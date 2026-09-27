"""Fill the database with synthetic reports so the dashboard has data for a demo.

Usage:  python -m app.demo_seed --count 200 --reset

Uses the offline rule engine only, so it makes no API calls.
All messages are synthetic examples, not real user data.
"""

import argparse
import random
from datetime import datetime, timedelta, timezone

from app.analyzer import ScamAnalyzer
from app.config import load_settings
from app.repository import ReportRepository

TEMPLATES: list[tuple[int, str]] = [
    (6, "พัสดุของท่านจัดส่งไม่ได้ เนื่องจากที่อยู่ไม่ครบ กรุณาอัปเดตภายใน 24 ชม. ที่ {parcel_domain}"),
    (4, "Kerry: พัสดุตกค้าง กรุณาชำระค่าธรรมเนียม {small_amount} บาท ที่ {parcel_domain} ด่วน"),
    (3, "ไปรษณีย์ไทย: พัสดุถูกตีกลับ ยืนยันที่อยู่ที่ https://{parcel_domain}/track"),
    (4, "{bank} แจ้งเตือน บัญชีของท่านถูกระงับ กรุณายืนยันตัวตนที่ https://{bank_domain}/login"),
    (2, "{bank}: มีการทำรายการผิดปกติ กรุณากรอกข้อมูลบัตรเพื่อยกเลิกที่ {bank_domain} ภายในวันนี้"),
    (3, "เจ้าหน้าที่ตำรวจแจ้งว่าบัญชีของท่านเกี่ยวข้องกับการฟอกเงิน ต้องโอนเงินเพื่อตรวจสอบ บัญชี {account} มิฉะนั้นจะออกหมายจับ"),
    (2, "DSI แจ้งว่าท่านมีหมายเรียกคดียาเสพติด ห้ามบอกใคร ให้แจ้ง OTP เพื่อยืนยันตัวตนทันที โทร {phone}"),
    (2, "กรมสรรพากรคืนเงินภาษี {big_amount} บาท กรอกข้อมูลบัตรเพื่อรับเงินคืนที่ bit.ly/{slug}"),
    (1, "การไฟฟ้า: ค่าไฟค้างชำระ จะถูกตัดไฟภายใน 24 ชม. ชำระด่วนที่ {bill_domain}"),
    (3, "ลงทุนคริปโต ผลตอบแทน {percent}% ต่อวัน การันตีไม่มีขาดทุน แอดไลน์ @{slug}"),
    (3, "รับสมัครงานออนไลน์ ทำงานที่บ้าน รายได้วันละ {big_amount} บาท แอดไลน์เลย"),
    (2, "แม่ หนูโทรศัพท์หาย ยืมเงินหน่อย ด่วนมาก โอนเงินเข้าบัญชีเพื่อนหนู {account_plain} ก่อนนะ"),
    (2, "ยินดีด้วย คุณถูกรางวัล iPhone ชำระค่าดำเนินการ {small_amount} บาท เพื่อรับรางวัลภายในวันนี้"),
    (4, "พรุ่งนี้ประชุมทีมตอน {hour} โมงนะ อย่าลืมเอาเอกสารมาด้วย"),
    (3, "พัสดุของคุณจัดส่งเรียบร้อยแล้ว ขอบคุณที่ใช้บริการ"),
    (2, "โปรโมชันเดือนนี้ ดูรายละเอียดได้ที่ https://www.kasikornbank.com"),
]

PARCEL_DOMAINS = ["parcel-th-update.cc", "kerry-th.top", "thaipost-track.xyz", "flash-delivery.vip"]
BANKS = [("SCB", "scb-secure.xyz"), ("KBank", "kbank-verify.top"), ("กรุงไทย", "ktb-online.icu")]
BILL_DOMAINS = ["pea-bill.online", "mea-pay.site"]
DEFAULT_DAYS = 60
RECENT_BURST_DOMAIN = "parcel-th-update.cc"
RECENT_BURST_COUNT = 5


def fill(template: str, rng: random.Random) -> str:
    bank, bank_domain = rng.choice(BANKS)
    return template.format(
        parcel_domain=rng.choice(PARCEL_DOMAINS),
        bank=bank,
        bank_domain=bank_domain,
        bill_domain=rng.choice(BILL_DOMAINS),
        small_amount=rng.choice([35, 49, 99, 150, 500]),
        big_amount=f"{rng.choice([1500, 2500, 4500, 12000]):,}",
        percent=rng.choice([5, 10, 20, 30]),
        account=f"{rng.randint(100, 999)}-{rng.randint(0, 9)}-{rng.randint(10000, 99999)}-{rng.randint(0, 9)}",
        account_plain=str(rng.randint(10**9, 10**10 - 1)),
        phone=f"08{rng.randint(0, 9)}-{rng.randint(100, 999)}-{rng.randint(1000, 9999)}",
        slug=rng.choice(["rich2026", "rd-refund", "win-now", "easy-money"]),
        hour=rng.choice([9, 10, 13, 15]),
    )


def random_time(rng: random.Random, now: datetime, days: int) -> datetime:
    # Squaring the fraction skews timestamps toward recent days, giving an upward trend.
    age = (rng.random() ** 2) * days
    return now - timedelta(days=age, minutes=rng.randint(0, 59))


def seed(repo: ReportRepository, count: int, days: int, rng: random.Random) -> None:
    analyzer = ScamAnalyzer()
    now = datetime.now(timezone.utc)
    weights = [w for w, _ in TEMPLATES]
    templates = [t for _, t in TEMPLATES]
    for _ in range(count):
        text = fill(rng.choices(templates, weights)[0], rng)
        repo.save(analyzer.analyze(text), text, source="seed", created_at=random_time(rng, now, days))

    burst = f"พัสดุของท่านจัดส่งไม่ได้ กรุณาอัปเดตภายใน 24 ชม. ที่ {RECENT_BURST_DOMAIN}"
    for i in range(RECENT_BURST_COUNT):
        repo.save(analyzer.analyze(burst), burst, source="seed", created_at=now - timedelta(hours=i + 1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--reset", action="store_true", help="delete existing reports first")
    parser.add_argument("--random-seed", type=int, default=42)
    args = parser.parse_args()

    repo = ReportRepository(load_settings().database_path)
    if args.reset:
        repo.clear()
    seed(repo, args.count, args.days, random.Random(args.random_seed))
    print(f"Seeded. Total reports: {repo.count()}")


if __name__ == "__main__":
    main()
