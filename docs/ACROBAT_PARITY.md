# Acrobat Pro parity checklist

Source of truth: the tool definitions shipped inside the locally installed **Adobe Acrobat Pro DC 22.002.20191**
(`Adobe Acrobat.app/Contents/Resources/AcroApp/ENU/*.aapp`, 41 tool definitions, 34 plug-ins), inventoried with
REA on 2026-10-18 (Info.plist evidence `ev_8c5c2f51…`). Only feature names and groupings were taken from Acrobat;
every feature here is implemented independently on PyMuPDF, pdf.js, Tesseract and pyHanko.

Status: ✅ done and tested · 🟡 partial (see note) · ❌ not yet · ☁️ cloud-only in Acrobat, out of scope for a local app.

## Summary

Counted over the checklist rows below (a row can group related commands).

| Status | Rows |
| --- | --- |
| ✅ Done | 67 |
| 🟡 Partial | 11 |
| ❌ Not yet | 26 |
| ☁️ Out of scope (cloud) | 3 plus the cloud services listed at the end |

## Edit PDF (`EditPDFApp`)

| Acrobat command | Status | LocalPDF |
| --- | --- | --- |
| TouchUpEditPDFTool (edit text) | ✅ | Click a paragraph, edit, reflows in its box; keeps the embedded font when it has the glyphs, otherwise a matching base-14 font |
| TouchUpAddTextbox | ✅ | Add text (font, size, color, bold/italic, alignment) |
| TouchUpAddImage | ✅ | Add image |
| TouchUpEditImage | 🟡 | Replace or delete images; no move/resize/crop of an existing image |
| LinkMenu / Link | ✅ | Web, mail and page links; delete links |
| Crop | ✅ | Drag to crop, or trim margins on any page set |
| HeaderFooter | ✅ | Six slots, `<<page>>`, `<<pages>>`, `<<date>>`, start number |
| Watermark | ✅ | Text or image, angle, opacity, behind/over content |
| BatesNumbering | ✅ | Prefix, suffix, start, digits, position |
| DocBackground | ✅ | Color or image |
| NewBookmark | ✅ | Add, rename, delete, auto-generate from headings |
| AddFileAttachment | ✅ | Embed and remove files |
| Thread (article threads) | ❌ | |
| Find & replace (Edit menu) | ✅ | Replace all occurrences |

## Comment (`CommentApp`)

| Acrobat command | Status | LocalPDF |
| --- | --- | --- |
| Highlight, Underline, StrikeOut | ✅ | From a text selection; also squiggly |
| Text (sticky note) | ✅ | |
| FreeText, FreeTextTypewriter, FreeTextCallout | ✅ | Text box, typewriter, callout with leader line |
| Line, LineArrow, Square, Circle | ✅ | |
| Polygon, PolygonCloud, PolyLine | ✅ | |
| Ink, EraseInk | ✅ | Freehand drawing and eraser |
| Stamp | ✅ | 14 standard stamps, custom image stamp, dated stamp |
| Caret | ✅ | Insert-text mark |
| Replace (replace text) | 🟡 | Use strikethrough plus an insert-text mark |
| FileAttachment | ✅ | Pushpin attachment |
| Sound | ❌ | |
| Replies, colour, edit, delete | ✅ | Comment popover on click; Delete key removes |
| CommentListMenu | ✅ | Comments panel in the sidebar |
| SortCommentsMenu, FilterCommentsMenu | ❌ | |
| Export comments | 🟡 | CSV and JSON; no FDF/XFDF |
| Flatten comments | ✅ | |

## Organize Pages (`PagesApp`)

| Acrobat command | Status | LocalPDF |
| --- | --- | --- |
| DeleteSelectedPages, RotatePagesCW/CCW | ✅ | Grid or thumbnails, multi-select |
| Reorder (drag) | ✅ | Drag thumbnails |
| ExtractSelectedPages | ✅ | Download or open as a new document |
| InsertPages | ✅ | Blank pages, or from a PDF/image |
| ReplacePages | ✅ | |
| SplitDocument | ✅ | By page count, ranges, top-level bookmarks or file size |
| CropPages | ✅ | |
| NumberPages | ✅ | Page labels (roman front matter, then 1, 2, 3) |
| Duplicate pages | ✅ | |
| BatesNumbering | ✅ | |
| Print | ✅ | Browser print dialog |
| PageProperties | 🟡 | Size and rotation shown; no per-page actions |
| InsertFromTemplate, Forms_PageTemplate | ❌ | |
| SetTransitions | ❌ | |

## Combine, Create, Export

| Acrobat command | Status | LocalPDF |
| --- | --- | --- |
| NewDocCombineFiles | ✅ | Open docs plus PDFs/images, one bookmark per file |
| Create PDF from images, text, HTML, EPUB, XPS | ✅ | Plus Markdown and blank documents |
| Create PDF from Word, Excel, PowerPoint | ❌ | Needs a local Office converter (LibreOffice) |
| Create PDF from web page, scanner | ❌ | |
| EXFT_MSWord | ✅ | pdf2docx |
| EXFT_MSExcel | ✅ | One sheet per detected table |
| EXFT_MSPowerPoint | 🟡 | One slide per page as an image with the page text as notes; not editable shapes |
| EXFT_RTF_K | ❌ | |
| Export to images, text, HTML | ✅ | Plus Markdown |

## Fill & Sign (`FillSignApp`)

| Acrobat command | Status | LocalPDF |
| --- | --- | --- |
| FSS:Tool:Text | ✅ | |
| Crosscheck, Checkmark, Circle, Line, Dot | ✅ | |
| FSS:DigSig (signature, initials) | ✅ | Draw, type or image; placed by dragging |
| Date | ✅ | |
| FSS:Tool:InviteOthers | ☁️ | |

## Prepare Form (`FormsApp`)

| Acrobat command | Status | LocalPDF |
| --- | --- | --- |
| Forms_CreateNewForm, add fields | ✅ | Text (multi-line), checkbox, radio, dropdown, list, signature, button |
| FindsFormFields (auto-detect) | ✅ | Underscore runs, drawn lines, small boxes |
| Edit field properties | 🟡 | Name, tooltip, required, read-only, options, position; no calculations, formats or actions |
| Forms_Highlight | ✅ | Fill mode outlines fields; required fields marked |
| Forms_ClearForm | ✅ | Read-only fields keep their value |
| Forms_ImportData, FormData_ExportData | 🟡 | JSON and CSV; no FDF/XFDF/XML |
| Advanced_CreateSpreadsheet | ❌ | |
| Forms_DistributeForm, TrackReturnedForms | ☁️ | |

## Protect and Redact

| Acrobat command | Status | LocalPDF |
| --- | --- | --- |
| RestrictWithPassword | ✅ | AES-256, open and permissions passwords, six permission switches |
| Remove security | ✅ | Needs the permissions password |
| Editing protected files | ✅ | Encryption and permissions are re-applied on every save; restricted files need the permissions password, as in Acrobat |
| RemoveHiddenInfo, SanitizeDocumentCmd | ✅ | Metadata, JavaScript, attachments, hidden text, links, form values |
| SecurityPolicyFavorites | ❌ | |
| ProtectMIPWithLabels | ☁️ | |
| Redact text / area | ✅ | |
| Find text & patterns to redact | ✅ | Words, regex, email, phone, SSN, card, date, IBAN, IP, URL |
| RedactApplyButton | ✅ | Removes the content, not just covers it |
| RedactToolProps | 🟡 | Overlay text and fill colour; no font or repeat options |

## Scan & OCR (`PaperToPDFApp`)

| Acrobat command | Status | LocalPDF |
| --- | --- | --- |
| P2P:ShowOCR (recognize text) | ✅ | Tesseract, invisible text layer, keeps the page image |
| Scan:OPT (optimize scans) | 🟡 | Via Compress PDF |
| Cpt:CapturePages from scanner | ❌ | |
| MagicCleanPerspectiveCorrection | ❌ | |
| ShowCaptureSuspects | ❌ | |

## Compare, Optimize, Stamp, Measure

| Acrobat command | Status | LocalPDF |
| --- | --- | --- |
| DIGSIG:CompareDocuments | ✅ | Word-level diff, change list, annotated copy |
| Visual (graphics) compare | ❌ | |
| CompressPDFAppCmd, ReduceFileSize | ✅ | Image downsampling, font subsetting, object clean-up |
| PDFOptimizer (advanced) | 🟡 | Three presets plus font/metadata switches |
| Fast web view (linearize) | ❌ | |
| AddStamp, CustomStamps | ✅ | |
| Measure distance, perimeter, area | ✅ | Unit and scale; kept as comments |
| GeoLocation | ❌ | |

## Certificates (`CertificatesApp`)

| Acrobat command | Status | LocalPDF |
| --- | --- | --- |
| DIGSIG:SignWithBoxDragOrClick | ✅ | PAdES signature with a .p12/.pfx or a self-signed ID created in the app |
| DIGSIG:ValidateAll | ✅ | Integrity, trust and coverage per signature |
| DIGSIG:TimestampDocument | ❌ | Needs a timestamp server (network) |
| DIGSIG:CertifyInvisible | ❌ | |

## Accessibility, Action Wizard, Properties, View

| Acrobat command | Status | LocalPDF |
| --- | --- | --- |
| AccCheck:DoCheck | 🟡 | 11 rules (tags, language, title, real text, fonts, bookmarks, field tooltips, security, alt text, contrast) |
| MakeAccessible, autotag, reading order, alt text | ❌ | |
| Action Wizard (run actions) | ✅ | Five built-in actions over any set of open documents |
| CreateWorkflow (custom actions) | ❌ | |
| Document properties | ✅ | Title, author, subject, keywords, facts |
| Read Out Loud | ✅ | Local system voices |
| Find, zoom, fit width, page navigation, thumbnails, tabs | ✅ | |
| Undo / redo | ✅ | 40 steps, covers every operation |

## Not started (Phase 3)

| Acrobat app | Status |
| --- | --- |
| PDF Standards (PDF/A, PDF/X, PDF/E), Preflight | ❌ |
| Print Production (output preview, inks, trapping, flattener) | ❌ |
| Rich Media (3D, video, sound, buttons) | ❌ |
| JavaScript tools | ❌ (also a deliberate security choice) |
| Index (catalog across files) | ❌ |
| Create Custom Tool | ❌ |

## Out of scope: Acrobat cloud services

Request E-signatures, Send in Bulk, Collect Payments, Add E-sign Branding, Create a Web Form, Share,
Unified Share, Send for Comments, Tracked Send, Collect Feedback, Add custom page (Creative Cloud Express),
invite others to sign, distribute/track forms and Microsoft Information Protection labels all depend on Adobe's
servers, which conflicts with the zero-egress goal.
