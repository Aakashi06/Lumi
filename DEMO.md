# Lumi demo

Open http://127.0.0.1:5173/ and choose **Make your knowledge graph**.

1. Add a readable PDF, Word `.docx`, or UTF-8 `.txt` / `.md` file.
2. Watch upload and processing feedback. Concepts appear as the document is mapped into SQLite in progressive NetworkX batches.
3. Zoom, drag to orbit, and select a concept to see its definition, relationships, and evidence.
4. Choose **Ask Lumi** in the concept panel, or ask a question in the chat.
5. Follow citations back to the uploaded document; PDF citations include page numbers.

Ready-to-upload examples are in `data/demo/`: Knowledge graph basics.pdf, Knowledge graph basics.docx, and Knowledge graph basics.txt. They contain real, short educational text. A prepared text example is already imported.

Example question: **How does vector search use embeddings?**

Supported: `.pdf`, `.docx`, `.txt`, `.md`, up to 12 MB. Legacy `.doc`, images, scanned PDFs without OCR, videos, and URL imports are unsupported in this version. Local inference takes time; the prepared example is useful for demonstrating an already-built graph.
