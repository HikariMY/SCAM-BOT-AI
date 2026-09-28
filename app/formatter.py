"""Thai chat replies for LINE."""

import re

from app.advice import HOTLINE, REPORT_SITE, advice_for
from app.models import ScamCategory

HELP_TEXT = (
    "วิธีใช้ง่ายๆ 👇\n\n"
    "1️⃣ ได้ SMS หรือข้อความแปลกๆ\n"
    "2️⃣ แคปหน้าจอ แล้วกดปุ่ม 📷 ส่งรูปให้ตรวจ ด้านล่าง\n"
    "     หรือกดค้างที่ข้อความ เลือก \"คัดลอก\" แล้วมาวางในแชทนี้\n"
    "3️⃣ รอสักครู่ บอทจะบอกว่าอันตรายไหม\n\n"
    "🔴 แดง = อันตราย ห้ามทำตาม\n"
    "🟡 เหลือง = น่าสงสัย ถามลูกหลานก่อน\n"
    "🟢 เขียว = ไม่พบอันตราย\n\n"
    f"สงสัยอะไร โทร {HOTLINE} ฟรี 24 ชม.\n"
    "(ผลตรวจเป็นการประเมินอัตโนมัติ ใช้ประกอบการตัดสินใจ)"
)

WELCOME_TEXT = (
    "สวัสดีครับ 🙏 ผมคือบอทช่วยตรวจข้อความมิจฉาชีพ\n\n"
    "ได้ข้อความแปลกๆ ส่งมาให้ผมดูก่อนได้เลย\n"
    "ส่งเป็นรูปแคปหน้าจอ หรือคัดลอกข้อความมาก็ได้\n\n"
    + HELP_TEXT
)

ASK_FOR_IMAGE_TEXT = (
    "📷 แคปหน้าจอข้อความที่สงสัย\n"
    "แล้วกดปุ่ม \"📷 ส่งรูปให้ตรวจ\" ด้านล่าง เลือกรูปที่แคปไว้ได้เลย"
)
PRIVACY_TEXT = (
    "🔒 ความเป็นส่วนตัว\n\n"
    "• ไม่เก็บข้อความหรือรูปที่คุณส่งมา เก็บเพียงรหัสแทนข้อความ (hash) "
    "และลิงก์ เบอร์โทร เลขบัญชีที่พบ เพื่อทำสถิติกลโกง\n"
    "• ไม่เก็บชื่อหรือ LINE ID ของคุณ\n"
    "• ข้อความจะถูกส่งให้ AI (Google Gemini) ช่วยวิเคราะห์ "
    "จึงไม่ควรส่งรหัสผ่าน OTP หรือเลขบัตรของตัวเองมา\n"
    "• บอทนี้จะไม่ขอเงิน รหัส หรือข้อมูลส่วนตัวจากคุณเด็ดขาด "
    "ถ้ามีใครอ้างว่าเป็นบอทนี้แล้วขอสิ่งเหล่านี้ คือมิจฉาชีพ"
)
DETAILS_NOT_FOUND_TEXT = "ไม่พบรายละเอียดของรายงานนี้แล้ว ลองส่งข้อความมาตรวจใหม่อีกครั้ง"

HOTLINE_TEXT = (
    f"สายด่วนแจ้งเหตุภัยออนไลน์: {HOTLINE} (24 ชม.)\n"
    f"แจ้งความออนไลน์: {REPORT_SITE}\n\n"
    "ถ้าโอนเงินไปแล้ว:\n"
    "1. โทรหาธนาคารของคุณเพื่อขออายัดบัญชีปลายทางทันที\n"
    f"2. โทร {HOTLINE}\n"
    "3. เก็บหลักฐาน เช่น สลิปโอนเงิน แชท และเบอร์โทร"
)

ASK_FOR_MESSAGE_TEXT = "✍️ วางข้อความที่สงสัยมาในแชทนี้ได้เลย ระบบจะตรวจให้ภายในไม่กี่วินาที"
TOO_SHORT_TEXT = (
    "ข้อความสั้นเกินไป ลองส่งข้อความที่สงสัยมาทั้งข้อความ\n"
    "หรือแคปหน้าจอแล้วกดปุ่ม 📷 ส่งรูปให้ตรวจ ด้านล่างได้เลย"
)
UNSUPPORTED_TEXT = "ตอนนี้บอทตรวจได้เฉพาะข้อความและรูปภาพ ลองแคปหน้าจอแล้วส่งเป็นรูปแทนนะ"
ERROR_TEXT = f"ขออภัย ระบบตรวจไม่สำเร็จชั่วคราว ลองใหม่อีกครั้ง หากเร่งด่วนโทร {HOTLINE}"


def defang(url: str) -> str:
    """Make a link non-clickable so users cannot open it from the bot reply."""
    return re.sub(r"^http", "hxxp", url, flags=re.IGNORECASE).replace(".", "[.]")


def format_details(record: dict) -> str:
    """Stored report laid out as the three NLP steps from the project slides.

    Shown when the user taps "ดูรายละเอียด", so family members (and the
    presentation audience) can see how the result was reached.
    """
    category = ScamCategory(record["category"])
    entities = record["entities"]

    lines = [f"รายละเอียดรายงาน {record['report_code']}", "",
             "1️⃣ จำแนกข้อความ (Text Classification)",
             f"• ประเภท: {category.thai_label} ({category.value})",
             f"• ความเสี่ยง: {record['risk']}%"]
    if record["impersonated_org"]:
        lines.append(f"• แอบอ้างเป็น: {record['impersonated_org']}")

    lines += ["", "2️⃣ สกัดข้อมูลสำคัญ (Named Entity Recognition)"]
    found = (
        ("ลิงก์", [defang(u) for u in entities.get("urls", [])]),
        ("เบอร์โทร", entities.get("phones", [])),
        ("เลขบัญชี", entities.get("accounts", [])),
        ("จำนวนเงิน", entities.get("amounts", [])),
        ("หน่วยงานที่อ้างถึง", entities.get("organizations", [])),
    )
    entity_lines = [f"• {label}: {', '.join(values)}" for label, values in found if values]
    lines += entity_lines or ["• ไม่พบลิงก์ เบอร์โทร หรือเลขบัญชี"]

    lines += ["", "3️⃣ สรุปเหตุผล (Text Summarization)"]
    if record["summary"]:
        lines.append(f"• {record['summary']}")
    if record["red_flags"]:
        lines.append(f"• จุดน่าสงสัย: {', '.join(record['red_flags'])}")

    lines += ["", f"💡 คำแนะนำ: {advice_for(category)}"]
    return "\n".join(lines)


def format_stats(stats: dict) -> str:
    totals = stats["totals"]
    lines = [
        "สถิติกลโกง 30 วันล่าสุด",
        f"ตรวจทั้งหมด {totals['total']} ข้อความ พบกลโกง {totals['scams']} ข้อความ",
    ]
    categories = [c for c in stats["by_category"] if c["category"] != ScamCategory.SAFE.value]
    if categories:
        lines.append("\nประเภทที่พบบ่อย:")
        lines += [f"• {c['label']}: {c['count']}" for c in categories[:4]]
    if stats["by_org"]:
        lines.append("\nหน่วยงานที่ถูกแอบอ้างบ่อย:")
        lines += [f"• {o['org']}: {o['count']}" for o in stats["by_org"][:3]]
    if stats["emerging_domains"]:
        lines.append("\nลิงก์อันตรายที่ระบาดใน 24 ชม.:")
        lines += [f"• {defang(d['domain'])} ({d['count']} ครั้ง)" for d in stats["emerging_domains"][:3]]
    return "\n".join(lines)
