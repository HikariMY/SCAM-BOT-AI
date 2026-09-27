# Scam Alert Bot

แชทบอทตรวจจับข้อความหลอกลวงและมิจฉาชีพ (Ingoude Company)

ออกแบบให้**ผู้สูงอายุและคนที่ไม่ถนัดเทคโนโลยี**ใช้ได้ง่าย ใช้ได้ 2 ทาง:

1. **LINE** (ช่องทางหลัก) — เพิ่มเพื่อนบอทครั้งเดียว แล้วส่งข้อความหรือ**รูปแคปหน้าจอ**มาให้ตรวจ
2. **เว็บบนมือถือ** — เปิดลิงก์ กดปุ่มใหญ่ "📷 ส่งรูปแคปหน้าจอ" หรือ "📋 วางข้อความ" และเพิ่มไว้ที่หน้าจอมือถือได้เหมือนแอป

ผลตรวจแสดงเป็นไฟจราจร ใช้คำง่ายๆ พร้อมปุ่มโทร 1441:

| สี | ความหมาย |
|---|---|
| 🔴 อันตราย! น่าจะเป็นมิจฉาชีพ | ความเสี่ยง 70% ขึ้นไป |
| 🟡 น่าสงสัย ระวังไว้ก่อน | ความเสี่ยง 40-69% หรือมีลักษณะกลโกง |
| 🟢 ไม่พบอันตรายชัดเจน | ความเสี่ยงต่ำ |

## ฟีเจอร์ตามสไลด์

| สไลด์ | ส่วนที่ทำ | ไฟล์หลัก |
|---|---|---|
| Text Classification | แยก PHISHING / MONEY_TRANSFER / IMPERSONATION / INVESTMENT / SAFE | `app/nlp/llm.py`, `app/nlp/rules.py` |
| Named Entity Recognition | ดึงเบอร์โทร, URL, เลขบัญชี, จำนวนเงิน, หน่วยงานที่ถูกแอบอ้าง | `app/nlp/entities.py`, `app/nlp/organizations.py` |
| Text Summarization | สรุปเหตุผล 1 ประโยค + จุดน่าสงสัย | `app/nlp/llm.py` |
| ตรวจลิงก์อันตราย | โดเมนเลียนแบบแบรนด์, TLD เสี่ยง, ลิงก์ย่อ, IP (ไม่เปิดลิงก์จริง) | `app/nlp/domains.py` |
| Risk Scoring | คะแนน 0-100% + ไฟจราจร + คำแนะนำภาษาง่าย | `app/analyzer.py`, `app/plain_language.py` |
| LINE Chatbot | การ์ดสี Flex Message, Rich Menu ปุ่มใหญ่, Quick Reply, ส่งรูปให้ตรวจ | `app/line_handler.py`, `app/line_flex.py` |
| Report ID | `SA-2026-0001` เรียงตามปี | `app/repository.py` |
| Dashboard | ประเภทกลโกง, หน่วยงานที่ถูกแอบอ้าง, แนวโน้มรายวัน/สัปดาห์/เดือน, แจ้งเตือนลิงก์ระบาด | `app/web/dashboard.html` |

## สถาปัตยกรรม

```
LINE (ข้อความ / รูป)  หรือ  เว็บมือถือ (/)
              │
              ▼
      FastAPI (app/main.py)
              │
              ▼
ScamAnalyzer ─► 0. รูป: Gemini อ่านข้อความในรูป (OCR)
                1. NER ด้วย regex (entities.py)
                2. ตรวจโดเมน (domains.py)
                3. Rule engine (rules.py)       ← ตัวสำรองเสมอ
                4. Gemini จัดประเภท (llm.py)
                5. รวมผล + ไฟจราจร + คำแนะนำ
              │
              ▼
SQLite (เก็บเฉพาะ hash + ตัวบ่งชี้) ─► /api/stats ─► Dashboard
```

ถ้า Gemini ใช้ไม่ได้ (ไม่มี key, โควตาเต็ม, เน็ตหลุด) ระบบตรวจข้อความด้วย rule engine ต่อได้ ส่วนการตรวจรูปต้องใช้ Gemini

## รันบนเครื่อง

ต้องมี Python 3.12 ขึ้นไป

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
copy .env.example .env
# แก้ .env ใส่ GEMINI_API_KEY (สร้างฟรีที่ https://aistudio.google.com/apikey)

.\.venv\Scripts\python.exe -m app.demo_seed --count 200 --reset   # ข้อมูลตัวอย่างให้ Dashboard
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --port 8000
```

- หน้าตรวจ (มือถือ): http://localhost:8000/
- Dashboard: http://localhost:8000/dashboard
- API docs: http://localhost:8000/docs

> อย่า commit ไฟล์ `.env` (อยู่ใน `.gitignore` แล้ว) Gemini free tier อาจนำข้อมูลไปใช้พัฒนาโมเดล
> ให้ทดสอบด้วยข้อความตัวอย่าง ไม่ใช่ข้อมูลส่วนตัวจริง

## นำขึ้นออนไลน์ด้วย Render (ฟรี)

1. **อัปโค้ดขึ้น GitHub** — สร้าง repository ใหม่ (Private ได้) แล้ว push โค้ดโปรเจกต์นี้
2. **สมัคร Render** ที่ https://render.com ด้วยบัญชี GitHub
3. กด **New → Blueprint** เลือก repository นี้ Render จะอ่าน `render.yaml` ให้อัตโนมัติ
4. กรอกค่าลับที่ Render ถาม:
   - `GEMINI_API_KEY`
   - `LINE_CHANNEL_SECRET`, `LINE_CHANNEL_ACCESS_TOKEN` (ดูหัวข้อถัดไป เว้นว่างก่อนได้)
5. กด **Apply** รอ build ประมาณ 2-5 นาที จะได้ลิงก์ เช่น `https://scam-alert-bot.onrender.com`
6. **กันเครื่องหลับ**: Render ฟรีจะหลับเมื่อไม่มีคนใช้ 15 นาที ครั้งแรกที่ปลุกจะช้า 30-60 วินาที
   สมัคร https://cron-job.org (ฟรี) ตั้งให้เรียก `https://<ลิงก์ของคุณ>/health` ทุก 10 นาที

ข้อจำกัดของแพ็กเกจฟรี: ข้อมูลใน SQLite จะหายเมื่อเครื่อง restart หรือ deploy ใหม่
ระบบจึงใส่ข้อมูลตัวอย่างให้ Dashboard อัตโนมัติ (`SEED_DEMO_IF_EMPTY=true`)

## เชื่อม LINE (ฟรี)

1. เข้า https://developers.line.biz/console/ สร้าง Provider และ LINE Official Account (แพ็กเกจฟรี) แล้วเปิด Messaging API
2. คัดลอก **Channel secret** (หน้า Basic settings) และกด Issue **Channel access token** (หน้า Messaging API)
   ไปใส่ใน Render → Environment แล้วกด Save (Render จะ deploy ใหม่เอง)
3. ที่ Messaging API → **Webhook URL** ใส่ `https://<ลิงก์ของคุณ>/callback` กด Verify แล้วเปิด **Use webhook**
4. ใน LINE Official Account Manager ปิด **Auto-reply messages** และ **Greeting messages** (บอทส่งคำทักทายเอง)
5. ติดตั้งเมนูปุ่มใหญ่ (Rich Menu) รันจากเครื่องตัวเองครั้งเดียว โดยใส่ token ใน `.env` ก่อน:
   ```powershell
   .\.venv\Scripts\python.exe -m scripts.setup_rich_menu
   ```
6. แชร์ **QR code** ของบอท (หน้า Messaging API) ให้ผู้ใช้สแกนเพิ่มเพื่อน ใส่ในสไลด์หรือโปสเตอร์ได้เลย

บอทใช้ Reply API ซึ่งไม่นับโควตาข้อความของแพ็กเกจฟรี

### สิ่งที่ผู้ใช้เห็นใน LINE

- **เมนูปุ่มใหญ่ใต้แชท**: 📷 ส่งรูปให้ตรวจ · ✍️ ตรวจข้อความ · 📞 โทร 1441 · ❓ วิธีใช้
- **ส่งรูปแคปหน้าจอ SMS ได้** ไม่ต้องคัดลอกข้อความเป็น
- ระหว่างตรวจจะเห็นจุด "..." ว่าบอทกำลังทำงาน
- **ผลเป็นการ์ดสี** ตัวใหญ่ มีปุ่ม "📞 โทร 1441 ปรึกษาฟรี" และ "ดูรายละเอียด" สำหรับลูกหลาน

รูปเมนูสร้างจาก `scripts/rich_menu/rich_menu.html` (แคปที่ 1250x843 ความละเอียด 2x ได้ `rich_menu.png` ขนาด 2500x1686)

## API

| Method | Path | คำอธิบาย |
|---|---|---|
| POST | `/api/analyze` | `{"text": "..."}` ผลวิเคราะห์ + `verdict` ภาษาง่าย (20 ครั้ง/นาที/IP) |
| POST | `/api/analyze-image` | `{"image": "data:image/jpeg;base64,..."}` อ่านข้อความจากรูปแล้ววิเคราะห์ (6 ครั้ง/นาที/IP, ไม่เกิน 5MB) |
| GET | `/api/stats?period=day\|week\|month` | สถิติสำหรับ Dashboard |
| POST | `/callback` | LINE webhook (ตรวจ `X-Line-Signature`) |
| GET | `/health` | สถานะ engine และ LINE |

ทุก response อยู่ในรูป `{"success": bool, "data": ..., "error": str | null}`

## ทดสอบ

```powershell
.\.venv\Scripts\python.exe -m pytest --cov=app --cov=scripts
```

## ความปลอดภัยและความเป็นส่วนตัว

- ไม่เก็บข้อความต้นฉบับ รูป หรือ LINE user ID เก็บเฉพาะ SHA-256 hash และตัวบ่งชี้ (ลิงก์ เบอร์ บัญชี)
- ไม่เปิดลิงก์ที่ผู้ใช้ส่งมา (ตรวจจากชื่อโดเมนอย่างเดียว) จึงไม่มีความเสี่ยง SSRF
- ตรวจชนิดไฟล์รูปจาก magic bytes ไม่เชื่อ content type ที่ client ส่งมา
- ข้อความผู้ใช้และข้อความในรูปถูกส่งให้ LLM พร้อมคำสั่งห้ามทำตามคำสั่งในข้อความ (กัน prompt injection) และตรวจผลด้วย schema
- คำแนะนำ ไฟจราจร และเบอร์สายด่วนเป็นข้อความคงที่ ไม่ได้ให้ AI สร้าง
- ลิงก์ในรายละเอียดถูกทำให้กดไม่ได้ เช่น `parcel-th-update[.]cc`

## ข้อจำกัด

- ผลลัพธ์เป็นการประเมินอัตโนมัติ อาจผิดพลาดได้ ใช้ประกอบการตัดสินใจเท่านั้น
- Rule engine ครอบคลุมรูปแบบกลโกงที่พบบ่อย รูปแบบใหม่ต้องอาศัย Gemini
- ตรวจรูปได้เฉพาะเมื่อตั้งค่า Gemini แล้ว
- Rate limiter เป็นแบบ in-memory เหมาะกับการรัน process เดียว
