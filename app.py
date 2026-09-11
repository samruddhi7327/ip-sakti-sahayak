from flask import Flask, render_template, request, jsonify
from pathlib import Path
import os
import re
import math
import base64
from html import escape

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

try:
    from docx import Document as DocxDocument
except Exception:
    DocxDocument = None

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB per request

# -----------------------------
# Curated starter knowledge base
# -----------------------------
DOCUMENTS = [
    {
        "id": "patent-basics",
        "title": "IP India — Patent basics / Patents Act, 1970",
        "source": "IP India (Government of India)",
        "url": "https://ipindia.gov.in/pages/patents/learn/basics-of-patents",
        "topics": ["patent", "novelty", "inventive step", "industrial application", "prior art"],
        "text": (
            "IP India explains that an invention under the Patents Act, 1970 is a new product or process "
            "involving an inventive step and capable of industrial application. Novelty considers whether the "
            "subject matter was anticipated by publication or use before the relevant priority date. Inventive "
            "step concerns technical advance/economic significance and non-obviousness."
        ),
    },
    {
        "id": "patent-exclusions",
        "title": "IP India — Inventions not patentable (Section 3)",
        "source": "IP India (Government of India)",
        "url": "https://ipindia.gov.in/acts/patent-act-1970/section-3",
        "topics": ["patent", "known substance", "traditional knowledge", "section 3", "efficacy"],
        "text": (
            "Section 3 of the Patents Act lists subject matter that is not treated as an invention. It includes "
            "certain discoveries and, subject to the statutory conditions, a new form of a known substance that "
            "does not result in the enhancement of the known efficacy of that substance. The exact claim and facts "
            "must be assessed against the current Act and rules."
        ),
    },
    {
        "id": "tkdl",
        "title": "Traditional Knowledge Digital Library (TKDL)",
        "source": "TKDL — CSIR / Ministry of Ayush",
        "url": "https://www.tkdl.res.in/",
        "topics": ["traditional knowledge", "TKDL", "prior art", "Ayurveda", "formulation"],
        "text": (
            "TKDL is a Government of India initiative associated with CSIR and the Ministry of Ayush. Its public "
            "site describes a database of codified/published traditional medicine literature, including Ayurveda, "
            "and explains its role in making traditional knowledge searchable for patent examination. Full database "
            "access is controlled under TKDL access arrangements."
        ),
    },
    {
        "id": "ayush-regulation",
        "title": "Ministry of Ayush — ASU&H regulatory framework",
        "source": "Ministry of Ayush (Government of India)",
        "url": "https://ayush.gov.in/resources/annualReport/Annual_Report_2022-2023_English.pdf",
        "topics": ["ayush", "regulation", "medicine", "licensing", "GMP", "ayurvedic drug"],
        "text": (
            "The Ministry of Ayush explains that licensing and enforcement for Ayurveda, Siddha and Unani drugs "
            "are handled through State/UT licensing authorities under the Drugs and Cosmetics Act, 1940 and Rules, "
            "including Rule 158B for ASU medicines. Requirements include applicable licensing, safety/effectiveness, "
            "GMP and pharmacopoeial quality requirements."
        ),
    },
    {
        "id": "ayush-labelling",
        "title": "Ministry of Ayush — ASU&H labelling advisory",
        "source": "Ministry of Ayush (Government of India)",
        "url": "https://ayush.gov.in/resources/pdf/quality_standards/Advisory.pdf",
        "topics": ["labelling", "advertising", "ayush", "regulation", "claims"],
        "text": (
            "A Ministry of Ayush advisory states that the Ministry itself does not grant manufacturing licences or "
            "approval for an Ayush drug/medicine; licensing is handled by the applicable State Drug Licensing Authority. "
            "The advisory also addresses labelling and advertising claims for licensed ASU&H products."
        ),
    },
    {
        "id": "trademark",
        "title": "IP India — Basics of Trade Marks",
        "source": "IP India (Government of India)",
        "url": "https://ipindia.gov.in/basics-of-trademarks",
        "topics": ["trademark", "brand", "logo", "mark", "classification", "goods"],
        "text": (
            "IP India describes a trade mark as a sign capable of distinguishing the goods or services of one person "
            "from those of others. Registrable marks can include words, logos, symbols, shape, colour combinations and "
            "certain sounds, subject to legal requirements. Goods and services are classified under the Nice system."
        ),
    },
    {
        "id": "biodiversity-abs",
        "title": "National Biodiversity Authority — Biological Diversity / ABS Regulations",
        "source": "National Biodiversity Authority (Government of India)",
        "url": "https://nbaindia.org/uploaded/pdf/GNABSREG_2025.pdf",
        "topics": ["biodiversity", "ABS", "access benefit sharing", "biological resource", "traditional knowledge"],
        "text": (
            "India's biodiversity framework regulates access to biological resources and associated knowledge and "
            "provides for fair and equitable sharing of benefits. The National Biodiversity Authority publishes the "
            "applicable regulations and procedures. Whether a particular activity is covered depends on the facts, "
            "the applicant and the resource/knowledge involved."
        ),
    },
    {
        "id": "international",
        "title": "IP India — Madrid Protocol / international trademark route",
        "source": "IP India (Government of India)",
        "url": "https://www.ipindia.gov.in/trade-marks-resources-guidelines",
        "topics": ["international", "global", "trademark", "madrid", "foreign"],
        "text": (
            "For international brand protection, IP India provides information on the Madrid Protocol route. "
            "International protection is jurisdiction-dependent, so applicants should check the rules and filing "
            "requirements applicable to each target market."
        ),
    },
]

STOPWORDS = set("""
the a an and or of to for in on is are can may this that with from how what which
my i have has do does be it as by into about should your their our you user product
""".split())
LANGUAGE_NAMES = {"English": "English", "Hindi": "Hindi", "Marathi": "Marathi"}
ALLOWED_UPLOADS = {
    "image/png": "image",
    "image/jpeg": "image",
    "image/webp": "image",
    "application/pdf": "file",
    "text/plain": "file",
    "text/markdown": "file",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "file",
}


def tokenize(text):
    return [w for w in re.findall(r"[\w]+", text.lower(), flags=re.UNICODE) if w not in STOPWORDS]


def lexical_score(query, document):
    q = set(tokenize(query))
    d = set(tokenize(document["title"] + " " + document["text"] + " " + " ".join(document["topics"])))
    if not q or not d:
        return 0.0
    overlap = len(q & d)
    phrase_bonus = sum(0.25 for topic in document["topics"] if topic in query.lower())
    return overlap / math.sqrt(len(q)) + phrase_bonus


def retrieve(query, k=4):
    ranked = sorted(DOCUMENTS, key=lambda d: lexical_score(query, d), reverse=True)
    selected = [d for d in ranked[:k] if lexical_score(query, d) > 0]
    return selected or [DOCUMENTS[0]]


def classify_intent(query):
    q = query.lower()
    rules = {
        "patent": ["patent", "patentable", "invention", "inventive", "novel", "prior art", "पेटंट", "आविष्कार"],
        "traditional": ["traditional knowledge", "tkdl", "traditional", "पारंपरिक", "परंपरागत"],
        "trademark": ["trademark", "trade mark", "brand", "logo", "ट्रेडमार्क", "ब्रँड"],
        "regulation": ["regulation", "license", "licence", "medicine", "cosmetic", "ayush", "label", "advert", "नियम", "परवाना", "औषध"],
        "biodiversity": ["biodiversity", "biological resource", "abs", "benefit sharing", "medicinal plant", "जैवविविधता", "वनस्पती"],
        "international": ["international", "abroad", "foreign", "global", "other country", "overseas", "आंतरराष्ट्रीय", "विदेश"],
    }
    intents = [intent for intent, words in rules.items() if any(w in q for w in words)]
    return intents or ["general"]


def curated_fallback(query, language, docs, intents, attachment_note=""):
    primary = intents[0]
    openings = {
        "English": {
            "patent": "A patent may be an option for an Ayurvedic formulation, but the specific invention must satisfy the applicable patentability requirements.",
            "traditional": "For traditional Ayurvedic knowledge, an important first check is whether the same knowledge is already published or documented as prior art.",
            "trademark": "A trademark can be a separate IP route for protecting an Ayurvedic brand name or logo, subject to the applicable requirements.",
            "regulation": "The regulatory path for an Ayurveda-related product depends on its classification, intended use and how it will be marketed.",
            "biodiversity": "If an Ayurvedic product uses Indian biological resources or associated traditional knowledge, applicable biodiversity and Access and Benefit Sharing requirements may need to be checked.",
            "international": "International protection is jurisdiction-specific; protection obtained in India does not automatically apply in other countries.",
            "general": "I searched the relevant IP-SAKTI knowledge records for your question. The most relevant guidance and sources are below.",
        },
        "Hindi": {
            "patent": "हाँ, किसी आयुर्वेदिक formulation के लिए patent एक विकल्प हो सकता है, लेकिन उसे लागू patentability requirements पूरी करनी होंगी।",
            "traditional": "पारंपरिक आयुर्वेदिक ज्ञान के लिए पहले यह देखना महत्वपूर्ण है कि वही ज्ञान पहले से प्रकाशित या documented prior art तो नहीं है।",
            "trademark": "आयुर्वेदिक brand name या logo के लिए trademark protection एक अलग IP विकल्प हो सकता है।",
            "regulation": "आयुर्वेदिक product का regulatory path उसकी category, intended use और marketing पर निर्भर करता है।",
            "biodiversity": "यदि product में भारतीय biological resources या associated traditional knowledge शामिल है, तो biodiversity और Access and Benefit Sharing requirements की जाँच आवश्यक हो सकती है।",
            "international": "अंतरराष्ट्रीय protection के लिए target country के नियम अलग हो सकते हैं; भारत की protection अपने आप दूसरे देशों में लागू नहीं होती।",
            "general": "मैंने आपके प्रश्न से संबंधित IP-SAKTI knowledge records खोजे हैं। नीचे relevant guidance और sources दिए हैं।",
        },
        "Marathi": {
            "patent": "आयुर्वेदिक formulation साठी patent हा पर्याय असू शकतो; मात्र त्या invention ने लागू patentability requirements पूर्ण करणे आवश्यक आहे.",
            "traditional": "पारंपरिक आयुर्वेदिक ज्ञानासाठी तेच ज्ञान आधी प्रकाशित किंवा documented prior art म्हणून उपलब्ध आहे का हे तपासणे महत्त्वाचे आहे.",
            "trademark": "आयुर्वेदिक brand name किंवा logo साठी trademark protection हा स्वतंत्र IP पर्याय असू शकतो.",
            "regulation": "आयुर्वेदिक product चा regulatory path त्याची category, intended use आणि marketing यावर अवलंबून असतो.",
            "biodiversity": "भारतीय biological resources किंवा associated traditional knowledge वापरले असल्यास biodiversity आणि Access and Benefit Sharing requirements तपासणे आवश्यक असू शकते.",
            "international": "आंतरराष्ट्रीय protection साठी target country चे नियम वेगळे असू शकतात; भारतातील protection आपोआप इतर देशांत लागू होत नाही.",
            "general": "मी तुमच्या प्रश्नाशी संबंधित IP-SAKTI knowledge records शोधले आहेत. खाली relevant guidance आणि sources दिले आहेत.",
        },
    }
    actions = {
        "English": "Next step: review the cited official source and verify your exact facts/claim with an IP professional or relevant regulator before acting.",
        "Hindi": "अगला कदम: cited official source देखें और कार्रवाई से पहले अपने exact facts/claim की पुष्टि IP professional या संबंधित regulator से करें।",
        "Marathi": "पुढील पाऊल: cited official source तपासा आणि कृती करण्यापूर्वी तुमच्या exact facts/claim ची पुष्टी IP professional किंवा संबंधित regulator कडून घ्या.",
    }
    evidence = "\n\n".join([f"• {d['title']}: {d['text']}" for d in docs[:3]])
    attachment_text = f"\n\n{attachment_note}" if attachment_note else ""
    return f"{openings[language][primary]}\n\n{evidence}{attachment_text}\n\n{actions[language]}"


def extract_local_text(upload):
    """Best-effort local extraction for PDFs/text/DOCX when no API key is configured."""
    mime = upload.mimetype
    raw = upload.read()
    upload.seek(0)
    if mime == "application/pdf" and PdfReader:
        try:
            import io
            reader = PdfReader(io.BytesIO(raw))
            return "\n".join((page.extract_text() or "") for page in reader.pages)[:20000]
        except Exception:
            return ""
    if mime in {"text/plain", "text/markdown"}:
        try:
            return raw.decode("utf-8", errors="ignore")[:20000]
        except Exception:
            return ""
    if mime.endswith("wordprocessingml.document") and DocxDocument:
        try:
            import io
            doc = DocxDocument(io.BytesIO(raw))
            return "\n".join(p.text for p in doc.paragraphs)[:20000]
        except Exception:
            return ""
    return ""


def attachment_payload(upload):
    if not upload or not upload.filename:
        return None
    mime = upload.mimetype or "application/octet-stream"
    kind = ALLOWED_UPLOADS.get(mime)
    if not kind:
        raise ValueError("Unsupported file type. Use PNG, JPG/JPEG, WEBP, PDF, TXT, MD or DOCX.")
    raw = upload.read()
    upload.seek(0)
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError("File is too large. Please keep uploads under 8 MB.")
    return {
        "filename": upload.filename,
        "mime": mime,
        "kind": kind,
        "raw": raw,
        "data_url": f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}" if kind == "image" else None,
    }


def llm_answer(query, language, docs, attachment=None):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or OpenAI is None:
        return None

    client = OpenAI(api_key=api_key)
    context = "\n\n".join(
        f"SOURCE {i+1}\nTitle: {d['title']}\nURL: {d['url']}\nContent: {d['text']}"
        for i, d in enumerate(docs)
    )
    user_text = f"""You are IP-SAKTI Sahayak, a multilingual information assistant for Ayurveda-related intellectual property and regulatory guidance.

User question: {query or '[No typed question; infer the request from the attachment.]'}
Response language: {language}

Use ONLY the supplied official-source context for legal/regulatory claims. Do not invent laws, sections, approvals, deadlines, fees, case outcomes, or eligibility. If the sources are insufficient, say so clearly. Treat any uploaded image/document as user-provided evidence, not as an authoritative legal source. Do not make a definitive legal determination from an image. This is informational guidance, not legal advice.

Write a concise but useful answer in {language} with this structure:
1. Direct answer in 1-2 sentences.
2. What the uploaded item appears to show or contain, if an attachment was supplied.
3. Key considerations (2-4 bullets).
4. Suggested next step.
Do not add a fake citation list; the application displays retrieved official sources separately.

SOURCE CONTEXT:
{context}
"""

    content = [{"type": "input_text", "text": user_text}]
    if attachment:
        if attachment["kind"] == "image":
            content.append({"type": "input_image", "image_url": attachment["data_url"], "detail": "high"})
        else:
            content.append({
                "type": "input_file",
                "filename": attachment["filename"],
                "file_data": base64.b64encode(attachment["raw"]).decode("ascii"),
            })

    response = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
        input=[{"role": "user", "content": content}],
    )
    return response.output_text.strip()


@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": "File is too large. Please keep uploads under 8 MB."}), 413


@app.route("/")
def home():
    return render_template("index.html")


@app.post("/ask")
def ask():
    # Multipart form lets the same endpoint handle text + image/document uploads.
    query = (request.form.get("query") or "").strip()
    language = request.form.get("language", "English")
    if language not in LANGUAGE_NAMES:
        language = "English"

    upload = request.files.get("attachment")
    attachment = None
    attachment_note = ""
    extracted_text = ""

    try:
        if upload and upload.filename:
            attachment = attachment_payload(upload)
            if not query:
                query = "Please analyze this uploaded Ayurveda/IP/regulatory item and explain what I should check."
            if not os.getenv("OPENAI_API_KEY"):
                extracted_text = extract_local_text(upload)
                if extracted_text:
                    query_for_retrieval = f"{query}\n\nUploaded document text:\n{extracted_text[:12000]}"
                else:
                    query_for_retrieval = query
                    attachment_note = (
                        f"Attachment received: {attachment['filename']}. Image/document understanding is enabled when an OPENAI_API_KEY is configured."
                    )
            else:
                query_for_retrieval = query
        else:
            query_for_retrieval = query

        if not query:
            return jsonify({"error": "Please enter a question or attach a file."}), 400

        docs = retrieve(query_for_retrieval, k=4)
        intents = classify_intent(query)

        try:
            answer = llm_answer(query, language, docs, attachment=attachment)
        except Exception as exc:
            app.logger.exception("LLM request failed: %s", exc)
            answer = None

        if not answer:
            answer = curated_fallback(query, language, docs, intents, attachment_note=attachment_note)
            mode = "Curated RAG fallback"
            if attachment and not extracted_text and not os.getenv("OPENAI_API_KEY"):
                mode = "RAG fallback • attachment preview only"
        else:
            mode = "Multimodal LLM + RAG" if attachment else "LLM + RAG"

        return jsonify({
            "answer": answer,
            "language": language,
            "mode": mode,
            "intents": intents,
            "attachment": {"filename": attachment["filename"], "kind": attachment["kind"]} if attachment else None,
            "sources": [{"title": d["title"], "source": d["source"], "url": d["url"]} for d in docs],
            "disclaimer": {
                "English": "Information only — not legal advice. Verify current requirements in the original official sources.",
                "Hindi": "केवल जानकारी — कानूनी सलाह नहीं। वर्तमान आवश्यकताओं की पुष्टि मूल आधिकारिक स्रोतों में करें।",
                "Marathi": "केवळ माहिती — कायदेशीर सल्ला नाही. सध्याच्या आवश्यकतांची खात्री मूळ अधिकृत स्रोतांमध्ये करा."
            }.get(language),
        })
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
