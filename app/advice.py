"""Safety advice shown to users.

Kept as fixed text (never LLM-generated) so hotline numbers and instructions
are always correct.
"""

from app.models import ScamCategory

HOTLINE = "1441"
REPORT_SITE = "thaipoliceonline.go.th"

ADVICE = {
    ScamCategory.PHISHING: f"ห้ามกดลิงก์หรือกรอกข้อมูลใดๆ หากกรอกข้อมูลบัตรไปแล้วให้โทรอายัดบัตรกับธนาคารทันที และแจ้ง {HOTLINE}",
    ScamCategory.MONEY_TRANSFER: f"ห้ามโอนเงิน หากโอนไปแล้วให้โทร {HOTLINE} หรือธนาคารของคุณทันทีเพื่ออายัดบัญชีปลายทาง",
    ScamCategory.IMPERSONATION: f"หน่วยงานจริงไม่ขอให้โอนเงินหรือขอ OTP ทางโทรศัพท์/แชท ให้ติดต่อผ่านเบอร์ทางการเท่านั้น และแจ้ง {HOTLINE}",
    ScamCategory.INVESTMENT: "ไม่มีการลงทุนที่การันตีกำไรสูง ตรวจรายชื่อผู้ได้รับอนุญาตที่ ก.ล.ต. (sec.or.th) ก่อน และห้ามโอนเงิน",
    ScamCategory.SAFE: "ยังไม่พบความเสี่ยงชัดเจน แต่ถ้ามีลิงก์หรือขอเงิน ให้ตรวจสอบกับช่องทางทางการก่อนเสมอ",
}


def advice_for(category: ScamCategory) -> str:
    return ADVICE[category]
