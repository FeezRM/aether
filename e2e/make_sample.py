"""Write the sample contract used by the end-to-end test to the given path."""

import sys

import pymupdf as fitz

SECTION = """
<h1>Master Services Agreement</h1>
<p>This Master Services Agreement (the "Agreement") is entered into between Acme Corp ("Client") and
Northwind Labs ("Provider"). Contact: legal@acme.example or 555-201-3344.</p>
<h2>1. Services</h2>
<p>Provider shall deliver the software development services described in each Statement of Work.
Each Statement of Work forms part of this Agreement.</p>
<h2>2. Fees and Payment</h2>
<p>Client shall pay all undisputed invoices within thirty (30) days. Late payments accrue interest at
1.5% per month. Wire transfers go to IBAN DE89370400440532013000.</p>
<h2>3. Confidentiality</h2>
<p>Each party shall keep the other party's Confidential Information secret and use it only to
perform this Agreement. The employee SSN 123-45-6789 provided for background checks is
Confidential Information.</p>
<h2>4. Term and Termination</h2>
<p>This Agreement starts on 01/15/2026 and continues for two years. Either party may terminate
for material breach on thirty days written notice.</p>
<h2>5. Signatures</h2>
<p>Client name: ____________________</p>
<p>Date: ____________________</p>
"""


def main(path: str) -> None:
    story = fitz.Story(html=SECTION * 2, user_css="body{font-family:serif;font-size:11pt} h1{font-size:22pt} h2{font-size:14pt}")
    writer = fitz.DocumentWriter(path)
    mediabox = fitz.paper_rect("letter")
    more = True
    while more:
        device = writer.begin_page(mediabox)
        more, _ = story.place(mediabox + (60, 60, -60, -60))
        story.draw(device)
        writer.end_page()
    writer.close()


if __name__ == "__main__":
    main(sys.argv[1])
