# -*- coding: utf-8 -*-
#
#  Copyright 2020, 2021 Ramil Nugmanov <nougmanoff@protonmail.com>
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
from typing import Type, Union
from .core import Core
from .element import Element
from ..._functions import tuple_hash
from ...exceptions import IsNotConnectedAtom


class Dynamic(Core):
    __slots__ = ()

    @Core.charge.setter
    def charge(self, charge):
        try:
            g = self._graph()
            g._charges[self._map] = g._validate_charge(charge)
            g.flush_cache()
        except AttributeError:
            raise IsNotConnectedAtom

    @Core.is_radical.setter
    def is_radical(self, is_radical):
        try:
            g = self._graph()
            g._radicals[self._map] = g._validate_radical(is_radical)
            g.flush_cache()
        except AttributeError:
            raise IsNotConnectedAtom

    @property
    def p_charge(self) -> int:
        try:
            return self._graph()._p_charges[self._map]
        except AttributeError:
            raise IsNotConnectedAtom

    @p_charge.setter
    def p_charge(self, charge):
        try:
            g = self._graph()
            g._p_charges[self._map] = g._validate_charge(charge)
            g.flush_cache()
        except AttributeError:
            raise IsNotConnectedAtom

    @property
    def p_is_radical(self) -> bool:
        try:
            return self._graph()._p_radicals[self._map]
        except AttributeError:
            raise IsNotConnectedAtom

    @p_is_radical.setter
    def p_is_radical(self, is_radical):
        try:
            g = self._graph()
            g._p_radicals[self._map] = g._validate_radical(is_radical)
            g.flush_cache()
        except AttributeError:
            raise IsNotConnectedAtom

    @property
    def p_hybridization(self):
        """
        Product state hybridization of atom
        """
        try:
            return self._graph()._p_hybridizations[self._map]
        except AttributeError:
            raise IsNotConnectedAtom


class DynamicElement(Dynamic):
    __slots__ = ('__p_charge', '__p_is_radical')

    @property
    def atomic_symbol(self) -> str:
        return self.__class__.__name__[7:]

    @classmethod
    def from_symbol(cls, symbol: str) -> Type['DynamicElement']:
        """
        get DynamicElement class by its symbol
        """
        try:
            element = next(x for x in DynamicElement.__subclasses__() if x.__name__ == f'Dynamic{symbol}')
        except StopIteration:
            raise ValueError(f'DynamicElement with symbol "{symbol}" not found')
        return element

    @classmethod
    def from_atomic_number(cls, number: int) -> Type['DynamicElement']:
        """
        get DynamicElement class by its number
        """
        try:
            element = next(x for x in DynamicElement.__subclasses__() if x.atomic_number.fget(None) == number)
        except StopIteration:
            raise ValueError(f'DynamicElement with number "{number}" not found')
        return element

    @classmethod
    def from_atom(cls, atom: Union['Element', 'DynamicElement']) -> 'DynamicElement':
        """
        get DynamicElement object from Element object or copy of DynamicElement object
        """
        if isinstance(atom, Element):
            return cls.from_atomic_number(atom.atomic_number)(atom.isotope)
        elif not isinstance(atom, DynamicElement):
            raise TypeError('Element or DynamicElement expected')
        return atom.copy()

    @property
    def neighbors(self):
        try:
            return self._graph().neighbors(self._map)[0]
        except AttributeError:
            raise IsNotConnectedAtom

    @property
    def p_neighbors(self):
        try:
            return self._graph().neighbors(self._map)[1]
        except AttributeError:
            raise IsNotConnectedAtom

    def __eq__(self, other):
        """
        compare attached to molecules dynamic elements
        """
        return isinstance(other, DynamicElement) and self.atomic_number == other.atomic_number and \
            self.isotope == other.isotope and self.charge == other.charge and self.is_radical == other.is_radical and \
            self.p_charge == other.p_charge and self.p_is_radical == other.p_is_radical

    def __hash__(self):
        return tuple_hash((self.isotope or 0, self.atomic_number, self.charge, self.p_charge,
                           self.is_radical, self.p_is_radical))

    @property
    def is_dynamic(self) -> bool:
        """
        Atom has dynamic features
        """
        return self.charge != self.p_charge or self.is_radical != self.p_is_radical


__all__ = ['DynamicElement', 'Dynamic']
