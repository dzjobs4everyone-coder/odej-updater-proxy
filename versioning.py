# -*- coding: utf-8 -*-
"""ترقيم الإصدارات: صيغة واحدة فقط هي صيغة البرنامج الحالية  V01C-1006

    V  <رقم رئيسي 2 خانتين>  <حرف الدفعة>  -  <رقم البناء 4 خانات>

المقارنة: (الرئيسي، الحرف، البناء). فـ V01C-1007 > V01C-1006، و V01D-1001 > V01C-9999.
(الصيغة العشرية العادية كانت ستُقرأ خطأً: "1.0.8" أصغر من "V01C-1006" فلا يصل أي تحديث.)
نفس هذا الملف يُنسخ إلى الخادم وإلى أداة التوقيع وإلى البرنامج.
"""
import re

_RE = re.compile(r"V(\d{2})([A-Z])-(\d{4})")


def parse_version(v):
    m = _RE.fullmatch(str(v or "").strip().upper())
    if not m:
        raise ValueError(f"صيغة إصدار غير صالحة: {v!r} (المتوقع مثل V01C-1006)")
    return (int(m.group(1)), m.group(2), int(m.group(3)))


def is_valid(v):
    try:
        parse_version(v)
        return True
    except ValueError:
        return False


def is_newer(new, current):
    """True إذا كان new أحدث من current. إصدار current غير المفهوم (نسخة تطوير) يُعدّ الأقدم."""
    try:
        cur = parse_version(current)
    except ValueError:
        cur = (0, "", 0)
    return parse_version(new) > cur
