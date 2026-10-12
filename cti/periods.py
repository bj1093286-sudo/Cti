"""기간 필터(오늘/어제/이번 주/이번 달/직접 지정)와 직전 동일 기간 계산."""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

PRESETS = ("today", "yesterday", "this_week", "this_month", "custom")


@dataclass(frozen=True)
class Period:
    start: date  # 포함
    end: date  # 포함

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def dates(self) -> list[date]:
        return [self.start + timedelta(days=i) for i in range(self.days)]


def _clamp_day(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def resolve(preset: str, today: date, start: date | None = None,
            end: date | None = None) -> tuple[Period, Period]:
    """(현재 기간, 직전 동일 기간)을 돌려준다.

    - 오늘 ↔ 어제, 어제 ↔ 그제
    - 이번 주(월요일~오늘) ↔ 지난 주 월요일~같은 요일
    - 이번 달(1일~오늘) ↔ 지난 달 1일~같은 날짜(말일 초과 시 말일)
    - 직접 지정 ↔ 바로 앞의 같은 일수 구간
    """
    if preset == "today":
        cur = Period(today, today)
    elif preset == "yesterday":
        y = today - timedelta(days=1)
        cur = Period(y, y)
    elif preset == "this_week":
        cur = Period(today - timedelta(days=today.weekday()), today)
        return cur, Period(cur.start - timedelta(days=7), cur.end - timedelta(days=7))
    elif preset == "this_month":
        cur = Period(today.replace(day=1), today)
        py, pm = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
        return cur, Period(date(py, pm, 1), _clamp_day(py, pm, today.day))
    elif preset == "custom":
        if start is None or end is None:
            raise ValueError("직접 지정 기간에는 시작일과 종료일이 필요합니다.")
        if start > end:
            start, end = end, start
        if (end - start).days > 366:
            raise ValueError("조회 기간은 최대 367일입니다.")
        cur = Period(start, end)
    else:
        raise ValueError(f"알 수 없는 기간: {preset}")
    shift = timedelta(days=cur.days)
    return cur, Period(cur.start - shift, cur.end - shift)
