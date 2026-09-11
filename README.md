# IP-SAKTI Sahayak — Multimodal RAG MVP

SIH 2026 PS 26045 prototype for Ayurveda-focused IP and regulatory guidance.

## What was upgraded

- **Voice input:** browser microphone → speech-to-text (Chrome/Edge SpeechRecognition).
- **Voice output:** browser text-to-speech with English/Hindi/Marathi locale support.
- **Image analysis:** PNG/JPG/JPEG/WEBP upload. With `OPENAI_API_KEY`, the image is sent to a vision-capable model through the Responses API.
- **Document analysis:** PDF/TXT/MD/DOCX upload. With `OPENAI_API_KEY`, the document is sent to the model as a file input. Without a key, PDF/TXT/MD/DOCX text can be extracted locally where supported.
- **Multimodal RAG:** uploaded content is analyzed together with the retrieved IP-SAKTI official-source context.
- **Safer upload handling:** 8 MB request limit, MIME allow-list, no permanent local upload storage.
- **Source-cited UI:** retrieved official sources remain visible under each answer.

## Run locally

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

## Enable AI image/document understanding

Set an OpenAI API key as an environment variable. **Do not put the key in the source code or commit it to GitHub.**

Windows PowerShell:

```powershell
$env:OPENAI_API_KEY="YOUR_KEY_HERE"
$env:OPENAI_MODEL="gpt-5.6-luna"
python app.py
```

Render: add `OPENAI_API_KEY` and optionally `OPENAI_MODEL` under the service's Environment Variables. Never paste the secret into chat.

## Demo flow

1. Type a question, e.g. `Can I patent my Ayurvedic formulation?`
2. Or click **🎙️ Speak** and ask the question.
3. Or click **📎 Upload image / file** and select an Ayurvedic label, trademark/logo, patent document page, PDF, TXT, MD or DOCX.
4. Ask a question about the attachment, or leave the text box empty for a default analysis request.
5. Click **Ask IP-SAKTI**.
6. Use **🔊 Read answer** to hear the response.

## Important

This is an information-assistance prototype, not legal advice. Uploaded images/documents are user-provided evidence; official sources shown in the result remain the authoritative references for the RAG answer. Do not claim that the system grants legal rights, approves a product, or makes a definitive legal determination from an image.

## Render deployment

- Build: `pip install -r requirements.txt`
- Start: `gunicorn app:app`
- Add environment variable: `OPENAI_API_KEY`
- Optional: `OPENAI_MODEL=gpt-5.6-luna`

Uploads are processed in memory and are not saved to the Render filesystem.
