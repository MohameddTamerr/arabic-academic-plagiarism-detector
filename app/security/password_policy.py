# -*- coding: utf-8 -*-
"""
سياسة كلمات المرور المؤسسية (Institutional Password Policy):
- فرض حد أدنى لطول كلمة المرور (12 خانة افتراضياً).
- منع استخدام كلمات المرور الشائعة أو القابلة للتخمين (Offline Denylist).
- منع احتواء كلمة المرور على اسم المستخدم أو أجزاء من اسمه الكامل.
- إرجاع رسائل إرشادية عربية واضحة وآمنة دون تعقيدات عشوائية تعيق الاستخدام.
"""

from typing import Tuple, Optional
import config

_COMMON_DENYLIST = {
    '123456789012',
    '1234567890123',
    'password1234',
    'password12345',
    'admin1234567',
    'admin12345678',
    'qwertyuiop12',
    'policeacademy12',
    'police1234567',
    'administrator1',
    'academy123456',
    'mohamed123456',
    'darwish123456',
    'pass123456789',
    'welcome123456'
}


def validate_password_strength(
    password: str,
    username: str = '',
    full_name: str = '',
    min_length: Optional[int] = None
) -> Tuple[bool, str]:
    """
    التحقق من قوة كلمة المرور ومطابقتها للمعايير المؤسسية.
    
    :param password: كلمة المرور المراد فحصها
    :param username: اسم المستخدم المرتبط للتحقق من عدم التشابه
    :param full_name: الاسم الكامل للمستخدم
    :param min_length: الطول الأدنى المخصص (اختياري، الافتراضي من config)
    :return: (is_valid: bool, error_message: str)
    """
    if not password:
        return False, "كلمة المرور مطلوبة ولا يمكن أن تكون فارغة."

    required_length = min_length if min_length is not None else getattr(config, 'AUTH_PASSWORD_MIN_LENGTH', 12)
    if len(password) < required_length:
        return False, f"يجب ألا يقل طول كلمة المرور عن {required_length} خانة لضمان الأمان المؤسسي."

    clean_pass = password.strip().lower()

    # 1. فحص قائمة الكلمات المحظورة والشائعة
    if clean_pass in _COMMON_DENYLIST or clean_pass.startswith('12345678') or clean_pass.startswith('password'):
        return False, "كلمة المرور شائعة جداً وسهلة التخمين. يرجى اختيار كلمة مرور أكثر متانة."

    # 2. فحص عدم تطابق أو احتواء كلمة المرور على اسم المستخدم
    if username and len(username.strip()) >= 3:
        clean_user = username.strip().lower()
        if clean_user in clean_pass or clean_pass in clean_user:
            return False, "لا يجوز أن تحتوي كلمة المرور على اسم المستخدم الخاص بك."

    # 3. فحص عدم احتواء كلمة المرور على أجزاء بارزة من الاسم الكامل
    if full_name:
        parts = [p.strip().lower() for p in full_name.split() if len(p.strip()) >= 4]
        for part in parts:
            if part in clean_pass:
                return False, "لا يجوز أن تحتوي كلمة المرور على أجزاء من اسمك الشخصي."

    return True, ""
