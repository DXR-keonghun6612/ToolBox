"""문자열, OS, 시각 도우미. 다른 모듈을 모름."""

from __future__ import annotations
from enum import auto
from typing import (Tuple, Literal, TypeVar, Union)

from dataclasses import dataclass

import sys
import platform

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):
        @staticmethod
        def _generate_next_value_(name, start, count, last_values):
            return name.lower()
from os import get_terminal_size

from datetime import datetime, date, time, timezone
from dateutil.relativedelta import relativedelta


NUMBER = TypeVar("NUMBER", bound=Union[int, float])
PYTHON_VERSION = sys.version_info


class String():
    """String formatting helpers for CLI-oriented output."""
    @staticmethod
    def Count_auto_align(
        value: int, max_count: int, is_right: bool = True, fill: str = "0"
    ):
        """Builds a counter string with automatic width alignment.

        Args:
            value: Current counter value.
            max_count: Maximum counter value used to determine width.
            is_right: Whether to right-align the current value.
            fill: Fill character used for padding.

        Returns:
            A string such as ``"003/100"``.
        """
        if is_right:
            return f"{str(value).rjust(len(str(max_count)), fill)}/{max_count}"
        return f"{str(value).ljust(len(str(max_count)), fill)}/{max_count}"

    @staticmethod
    def Str_adjust(
        text: str,
        max_length: int,
        fill: str = " ",
        align: Literal["l", "c", "r"] = "r"
    ) -> Tuple[int, str]:
        """Pads a string to a target display width.

        Multibyte characters are treated as width ``2`` with a simple
        heuristic intended for terminal output.

        Args:
            text: Input text.
            max_length: Target display width.
            fill: Padding character.
            align: Alignment direction. One of ``"l"``, ``"c"``, or ``"r"``.

        Returns:
            A tuple of ``(overflow, adjusted_text)``.
        """
        visual_width = 0
        for char in text:
            if char.encode().isalpha() != char.isalpha():
                visual_width += 2
            else:
                visual_width += 1

        padding_size = max_length - visual_width
        if padding_size < 0:
            return -padding_size, text

        if align == "l":
            return 0, text + fill * padding_size
        if align == "c":
            left_padding = padding_size // 2
            right_padding = padding_size - left_padding
            return 0, fill * left_padding + text + fill * right_padding
        return 0, fill * padding_size + text

    @staticmethod
    def Progress_bar(
        iteration: int, total: int,
        prefix: str = '', suffix: str = '',
        decimals: int = 1, fill: str = '█'
    ):
        """Prints a terminal progress bar in-place.

        Args:
            iteration: Current step.
            total: Total number of steps.
            prefix: Text shown before the bar.
            suffix: Text shown after the bar.
            decimals: Decimal precision for the percentage.
            fill: Fill character used inside the bar.
        """
        _percentage = iteration / float(total)
        _str_p = ("{0:." + str(decimals) + "f}").format(100 * _percentage)

        _bias = len(prefix + _str_p + suffix) + 6
        _bar_l = get_terminal_size().columns - _bias
        _fill_l = round(_bar_l * _percentage)
        _str_b = fill * _fill_l + '-' * (_bar_l - _fill_l)

        print(f'\r{prefix} |{_str_b}| {_str_p}% {suffix}', end="\r")
        if iteration == total:
            print()


class Operating_System():
    """Operating system helpers."""

    THIS_STYLE = platform.system().lower()

    class Name(StrEnum):
        """Normalized OS names used by :class:`Operating_System`."""
        WINDOW = auto()
        LINUX = auto()

    @staticmethod
    def Matches_os(name: Operating_System.Name | str = "window"):
        """Checks whether the current OS matches a target name.

        Args:
            name: OS name or enum value to compare against.

        Returns:
            ``True`` if the current OS matches ``name``.
        """
        return Operating_System.THIS_STYLE == name


class Server():
    """Placeholder server interface with OS-aware branching hooks."""
    is_window: bool = Operating_System.Matches_os()

    @classmethod
    def Connect_to(cls):
        """Initializes a server connection.

        Raises:
            NotImplementedError: Always raised until a backend is implemented.
        """
        raise NotImplementedError

    @classmethod
    def Disconnect_to(cls):
        """Terminates a server connection.

        Raises:
            NotImplementedError: Always raised until a backend is implemented.
        """
        raise NotImplementedError


class Time_Utils():
    """Date and time helpers."""
    @staticmethod
    def Stamp(set_timezone: timezone | None = None):
        """Returns the current time.

        Args:
            set_timezone: Optional timezone for ``datetime.now``.

        Returns:
            The current ``datetime``.
        """
        return datetime.now(set_timezone)

    @staticmethod
    def Get_term(
        standard_time: datetime, set_timezone: timezone | None = None
    ):
        """Returns elapsed time from a reference timestamp.

        Args:
            standard_time: Reference datetime.
            set_timezone: Optional timezone applied to the current timestamp.

        Returns:
            A ``timedelta`` between now and ``standard_time``.
        """
        return Time_Utils.Stamp(set_timezone) - standard_time

    @staticmethod
    def Make_text_from(
        src: datetime | date | time | None = None, d_fmt: str | None = None
    ):
        """Formats a date/time object as text.

        Args:
            src: Source object. If omitted, the current time is used.
            d_fmt: Optional ``strftime`` format. If omitted, ISO format is used.

        Returns:
            A formatted date/time string.
        """
        _time = Time_Utils.Stamp() if src is None else src
        if d_fmt is None:
            return _time.isoformat()
        return _time.strftime(d_fmt)

    @staticmethod
    def Make_time_from(
        src: str, d_fmt: str | None = None,
        use_microsec: bool = False,
        use_timezone: bool = False
    ):
        """Parses text into a ``datetime``.

        Args:
            src: Input string to parse.
            d_fmt: Optional explicit ``strptime`` format.
            use_microsec: Whether to expect microseconds in the default ISO
                format.
            use_timezone: Whether to expect timezone info in the default ISO
                format.

        Returns:
            A parsed ``datetime`` instance.

        Raises:
            ValueError: If parsing fails.
        """
        if d_fmt is not None:
            _date_format = d_fmt
        else:  # iso
            _date_format = "%Y-%m-%dT%H:%M:%S"
            _date_format += ".%f" if use_microsec else ""
            _date_format += "%z" if use_timezone else ""

        _datetime = datetime.strptime(src, _date_format)
        return _datetime

    @dataclass
    class Relative():
        """Serializable wrapper for ``dateutil.relativedelta``.

        Attributes:
            years: Relative year offset.
            months: Relative month offset.
            weeks: Relative week offset.
            days: Relative day offset.
            hours: Relative hour offset.
            minutes: Relative minute offset.
            seconds: Relative second offset.
            microseconds: Relative microsecond offset.
        """
        years: int = 0
        months: int = 0
        weeks: int = 0
        days: int = 0
        hours: int = 0
        minutes: int = 0
        seconds: int = 0
        microseconds: int = 0

        @classmethod
        def from_delta(cls, delta: relativedelta) -> Time_Utils.Relative:
            """Builds a ``Relative`` instance from a ``relativedelta``."""
            return cls(
                years=delta.years,
                months=delta.months,
                weeks=delta.weeks,
                days=delta.days,
                hours=delta.hours,
                minutes=delta.minutes,
                seconds=delta.seconds,
                microseconds=delta.microseconds
            )

        def to_delta(self) -> relativedelta:
            """Converts the wrapper back to a ``relativedelta``."""
            return relativedelta(
                years=self.years,
                months=self.months,
                weeks=self.weeks,
                days=self.days,
                hours=self.hours,
                minutes=self.minutes,
                seconds=self.seconds,
                microseconds=self.microseconds
            )
