# -*- coding: utf-8 -*-
#
#  Copyright 2014-2021 Ramil Nugmanov <nougmanoff@protonmail.com>
#  This file is part of CGRtools.
#
#  CGRtools is free software; you can redistribute it and/or modify
#  it under the terms of the GNU Lesser General Public License as published by
#  the Free Software Foundation; either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#  GNU Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public License
#  along with this program; if not, see <https://www.gnu.org/licenses/>.
#
from bisect import bisect_left
from collections import defaultdict
from io import BytesIO
from logging import warning
from re import match, compile
from subprocess import check_output
from traceback import format_exc
from warnings import warn
from ._mdl import parse_error
from ._mdl import MDLRead, MDLWrite, MOLRead, EMOLRead, EMDLWrite
from ..exceptions import EmptyMolecule


head = compile(r'>\s.*<(.*)>')


class SDFRead(MDLRead):
    """
    MDL SDF files reader. works similar to opened file object. support `with` context manager.
    on initialization accept opened in text mode file, string path to file,
    pathlib.Path object or another buffered reader object
    """
    def __init__(self, file, indexable=False, **kwargs):
        """
        :param indexable: if True: supported methods seek, tell, object size and subscription, it only works when
            dealing with a real file (the path to the file is specified) because the external grep utility is used,
            supporting in unix-like OS the object behaves like a normal open file.

            if False: works like generator converting a record into MoleculeContainer and returning each object in
            order, records with errors are skipped
        :param ignore: Skip some checks of data or try to fix some errors.
        :param remap: Remap atom numbers started from one.
        :param store_log: Store parser log if exists messages to `.meta` by key `CGRtoolsParserLog`.
        :param calc_cis_trans: Calculate cis/trans marks from 2d coordinates.
        :param ignore_stereo: Ignore stereo data.
        """
        super().__init__(file, **kwargs)
        self.__file = iter(self._file.readline, '')
        self._data = self.__reader()
        next(self._data)

        if indexable:
            self._load_cache()

    @staticmethod
    def _get_shifts(file):
        shifts = [0]
        for x in BytesIO(check_output(['grep', '-bE', r'\$\$\$\$', file])):
            pos, line = x.split(b':', 1)
            shifts.append(int(pos) + len(line))
        return shifts

    def seek(self, offset):
        """
        shifts on a given number of record in the original file
        :param offset: number of record
        """
        if self._shifts:
            if 0 <= offset < len(self._shifts):
                current_pos = self._file.tell()
                new_pos = self._shifts[offset]
                if current_pos != new_pos:
                    if current_pos == self._shifts[-1]:  # reached the end of the file
                        self._file.seek(new_pos)
                        self.__file = iter(self._file.readline, '')
                        self._data = self.__reader()
                        next(self._data)
                        if offset:
                            self._data.send(offset)
                            self.__already_seeked = True
                    elif not self.__already_seeked:
                        self._file.seek(new_pos)
                        self._data.send(offset)
                        self.__already_seeked = True
                    else:
                        raise BlockingIOError('File already seeked. New seek possible only after reading any data')
            else:
                raise IndexError('invalid offset')
        else:
            raise self._implement_error

    def tell(self):
        """
        :return: number of records processed from the original file
        """
        if self._shifts:
            t = self._file.tell()
            return bisect_left(self._shifts, t)
        raise self._implement_error

    def __reader(self):
        im = 3
        failkey = False
        mkey = parser = record = None
        meta = defaultdict(list)
        file = self._file
        try:
            seekable = file.seekable()
        except AttributeError:
            seekable = False
        seek = yield  # init stop
        if seek is not None:
            yield
            pos = file.tell()
            count = seek
            self.__already_seeked = False
        else:
            pos = 0 if seekable else None
            count = 0
        for line in self.__file:
            if failkey and not line.startswith("$$$$"):
                continue
            elif parser:
                try:
                    if parser(line):
                        record = parser.getvalue()
                        parser = None
                except ValueError:
                    parser = None
                    self._info(f'line:\n{line}\nconsist errors:\n{format_exc()}')
                    seek = yield parse_error(count, pos, self._format_log(), {})
                    if seek is not None:  # seeked to start of mol block
                        yield
                        count = seek
                        pos = file.tell()
                        im = 3
                        mkey = None
                        meta = defaultdict(list)
                        self.__already_seeked = False
                    else:
                        failkey = True
                    self._flush_log()
            elif line.startswith("$$$$"):
                if record:
                    record['meta'].update(self._prepare_meta(meta))
                    if title:
                        record['title'] = title
                    try:
                        container = self._convert_structure(record)
                    except ValueError:
                        self._info(f'record consist errors:\n{format_exc()}')
                        seek = yield parse_error(count, pos, self._format_log(), record['meta'])
                    else:
                        if self._store_log:
                            log = self._format_log()
                            if log:
                                container.meta['CGRtoolsParserLog'] = log
                        seek = yield container
                    if seek is not None:  # seeked position
                        yield
                        count = seek - 1
                        self.__already_seeked = False
                    self._flush_log()
                    record = None

                if seekable:
                    pos = file.tell()
                count += 1
                im = 3
                failkey = False
                mkey = None
                meta = defaultdict(list)
            elif record:
                head_line = match(head, line)
                if head_line:
                    mkey = head_line.group(1).strip()
                    if not mkey:
                        self._info(f'invalid metadata entry: {line}')
                elif mkey:
                    data = line.strip()
                    if data:
                        meta[mkey].append(data)
            elif im:
                if im == 3:  # parse mol title
                    title = line.strip()
                im -= 1
            elif not im:
                try:
                    if 'V2000' in line:
                        try:
                            parser = MOLRead(line, self._log_buffer)
                        except EmptyMolecule:
                            if self._ignore:
                                parser = EMOLRead(self._log_buffer)
                                self._info(f'line:\n{line}\nconsist errors:\nempty atoms list. try to parse as V3000')
                            else:
                                raise
                    elif 'V3000' in line:
                        parser = EMOLRead(self._log_buffer)
                    else:
                        raise ValueError('invalid MOL entry')
                except ValueError:
                    self._info(f'line:\n{line}\nconsist errors:\n{format_exc()}')
                    seek = yield parse_error(count, pos, self._format_log(), {})
                    if seek is not None:  # seeked to start of mol block
                        yield
                        count = seek
                        pos = file.tell()
                        im = 3
                        mkey = None
                        meta = defaultdict(list)
                        self.__already_seeked = False
                    else:
                        failkey = True
                    self._flush_log()

        if record:  # True for MOL file only.
            record['meta'].update(self._prepare_meta(meta))
            if title:
                record['title'] = title
            try:
                container = self._convert_structure(record)
            except ValueError:
                self._info(f'record consist errors:\n{format_exc()}')
                log = self._format_log()
                self._flush_log()
                yield parse_error(count, pos, log, record['meta'])
            else:
                if self._store_log:
                    log = self._format_log()
                    if log:
                        container.meta['CGRtoolsParserLog'] = log
                self._flush_log()
                yield container

    __already_seeked = False


class SDFWrite(MDLWrite):
    """
    MDL SDF files writer. works similar to opened for writing file object. support `with` context manager.
    on initialization accept opened for writing in text mode file, string path to file,
    pathlib.Path object or another buffered writer object
    """
    def write(self, data):
        """
        write single molecule into file
        """
        mol = self._convert_structure(data)
        if isinstance(mol, list):
            self._file.write('$$$$\n'.join(mol))
        else:
            self._file.write(mol)

        for k, v in data.meta.items():
            self._file.write(f'>  <{k}>\n{v}\n')
        self._file.write('$$$$\n')


class ESDFWrite(EMDLWrite):
    """
    MDL V3000 SDF files writer. works similar to opened for writing file object. support `with` context manager.
    on initialization accept opened for writing in text mode file, string path to file,
    pathlib.Path object or another buffered writer object
    """
    def write(self, data):
        """
        write single molecule into file
        """
        mol = self._convert_structure(data)
        self._file.write(f'{data.name}\n\n\n  0  0  0     0  0            999 V3000\n')
        if isinstance(mol, list):
            self._file.write(f'M  END\n$$$$\n{data.name}\n\n\n  0  0  0     0  0            999 V3000\n'.join(mol))
        else:
            self._file.write(mol)
        self._file.write('M  END\n')

        for k, v in data.meta.items():
            self._file.write(f'>  <{k}>\n{v}\n')
        self._file.write('$$$$\n')


class SDFread:
    def __init__(self, *args, **kwargs):
        warn('SDFread deprecated. Use SDFRead instead', DeprecationWarning)
        warning('SDFread deprecated. Use SDFRead instead')
        self.__obj = SDFRead(*args, **kwargs)

    def __getattr__(self, item):
        return getattr(self.__obj, item)

    def __iter__(self):
        return iter(self.__obj)

    def __next__(self):
        return next(self.__obj)

    def __getitem__(self, item):
        return self.__obj[item]

    def __enter__(self):
        return self.__obj.__enter__()

    def __exit__(self, _type, value, traceback):
        return self.__obj.__exit__(_type, value, traceback)

    def __len__(self):
        return len(self.__obj)


class SDFwrite:
    def __init__(self, *args, **kwargs):
        warn('SDFwrite deprecated. Use SDFWrite instead', DeprecationWarning)
        warning('SDFwrite deprecated. Use SDFWrite instead')
        self.__obj = SDFWrite(*args, **kwargs)

    def __getattr__(self, item):
        return getattr(self.__obj, item)

    def __enter__(self):
        return self.__obj.__enter__()

    def __exit__(self, _type, value, traceback):
        return self.__obj.__exit__(_type, value, traceback)


__all__ = ['SDFRead', 'SDFWrite', 'ESDFWrite', 'SDFread', 'SDFwrite']
