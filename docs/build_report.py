"""
Generates docs/report.pdf - Parts 1 and 2 of the assignment.
3 pages max. UML sequence diagram is drawn directly with reportlab.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, KeepTogether, PageBreak,
)
from reportlab.graphics.shapes import Drawing, Line, String, Rect, Polygon, Group
from reportlab.graphics import renderPDF

OUT = "docs/report.pdf"
STUDENT = "M Zohaib Sajjad - bscs23098"

# --- UML sequence diagram as a proper reportlab Drawing ----------------------

def sequence_diagram():
    accent = HexColor("#1f4e79")
    red = HexColor("#b03030")
    green = HexColor("#1f7a3f")

    W, H = 16 * cm, 9.6 * cm
    d = Drawing(W, H)

    actors = ["Alice", "Bob", "API", "DB"]
    n = len(actors)
    x_left, x_right = 0.8 * cm, W - 0.8 * cm
    xs = [x_left + i * (x_right - x_left) / (n - 1) for i in range(n)]
    y_top = H - 0.4 * cm
    y_bot = 0.5 * cm

    # actor boxes + dashed lifelines
    for x, a in zip(xs, actors):
        d.add(Rect(x - 0.9*cm, y_top - 0.55*cm, 1.8*cm, 0.55*cm,
                   fillColor=accent, strokeColor=accent))
        d.add(String(x, y_top - 0.38*cm, a, fontName="Helvetica-Bold",
                     fontSize=9, fillColor=white, textAnchor="middle"))
        ln = Line(x, y_top - 0.55*cm, x, y_bot, strokeColor=accent,
                  strokeDashArray=[2, 2])
        d.add(ln)

    def arrow(y, x1, x2, label, colour=black, dashed=False):
        ln = Line(x1, y, x2, y, strokeColor=colour, strokeWidth=0.7)
        if dashed:
            ln.strokeDashArray = [2, 2]
        d.add(ln)
        # arrowhead
        dx = 0.15 * cm if x2 > x1 else -0.15 * cm
        d.add(Polygon([x2, y, x2 - dx, y + 0.08*cm, x2 - dx, y - 0.08*cm],
                      fillColor=colour, strokeColor=colour))
        d.add(String((x1 + x2) / 2, y + 0.1*cm, label,
                     fontName="Helvetica", fontSize=7.5,
                     fillColor=colour, textAnchor="middle"))

    ax, bx, apix, dbx = xs
    y = y_top - 1.0 * cm
    STEP, GAP = 0.5 * cm, 0.7 * cm

    arrow(y, ax,   apix, "GET /documents/d1");                       y -= STEP
    arrow(y, apix, dbx,  "SELECT content, version");                 y -= STEP
    arrow(y, dbx,  apix, '("hello", v=1)', dashed=True);             y -= STEP
    arrow(y, apix, ax,   "200 {content, version: 1}", dashed=True);  y -= GAP

    arrow(y, bx,   apix, "GET /documents/d1");                       y -= STEP
    arrow(y, apix, bx,   "200 {content, version: 1}", dashed=True);  y -= GAP

    arrow(y, ax,   apix, "PUT {content: 'A', version: 1}", green);   y -= STEP
    arrow(y, apix, dbx,  "UPDATE ... WHERE version = 1", green);     y -= STEP
    arrow(y, dbx,  apix, "1 row affected (now v=2)", green, True);   y -= STEP
    arrow(y, apix, ax,   "200 {version: 2}", green, True);           y -= GAP

    arrow(y, bx,   apix, "PUT {content: 'B', version: 1}", red);     y -= STEP
    arrow(y, apix, dbx,  "UPDATE ... WHERE version = 1", red);       y -= STEP
    arrow(y, dbx,  apix, "0 rows affected", red, True);              y -= STEP
    arrow(y, apix, bx,   "409 Conflict {current: 2}", red, True);    y -= 0.55*cm

    d.add(String(x_left, y,
                 "Bob refetches v=2, merges, retries - nothing is silently lost.",
                 fontName="Helvetica-Oblique", fontSize=8, fillColor=black))
    return d


# --- Document assembly --------------------------------------------------------

styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Heading1"], textColor=HexColor("#1f4e79"),
                    spaceBefore=4, spaceAfter=4, fontSize=14)
H2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=HexColor("#1f4e79"),
                    spaceBefore=4, spaceAfter=2, fontSize=11)
BODY = ParagraphStyle("BODY", parent=styles["BodyText"], fontSize=9.5, leading=12.5,
                      alignment=TA_JUSTIFY, spaceAfter=4)
META = ParagraphStyle("META", parent=styles["BodyText"], fontSize=8.5, leading=11,
                      textColor=HexColor("#555555"))


def P(text): return Paragraph(text, BODY)


doc = SimpleDocTemplate(OUT, pagesize=A4,
                        leftMargin=1.6*cm, rightMargin=1.6*cm,
                        topMargin=1.4*cm, bottomMargin=1.4*cm,
                        title="StudySync Resilience Report",
                        author=STUDENT)

story = []

# Header
story += [
    Paragraph("Building Resilient Distributed Systems - StudySync", H1),
    Paragraph(f"{STUDENT} &nbsp;&nbsp;|&nbsp;&nbsp; PDC Assignment 4", META),
    Spacer(1, 0.2*cm),
]

# --- Part 1 ---------------------------------------------------------------
story += [
    Paragraph("Part 1 - Analysis: where the naive architecture breaks", H1),

    Paragraph("Problem 1 - Lost update on concurrent document edits", H2),
    P("The sync issue lives in the read-modify-write window inside the API request "
      "lifecycle. Alice reads document <i>d1</i> at version 1 into her client; Bob does "
      "the same a moment later. Both clients now hold the same snapshot. Alice PUTs her "
      "edit, the backend issues an unconditional <code>UPDATE documents SET content = ?</code>, "
      "and writes through. Bob then PUTs his edit and his unconditional UPDATE overwrites "
      "Alice's row. The database commits the second write happily because nothing in the "
      "statement asserts what Bob believed the prior state to be. No row-level lock, no "
      "version check, no serializable isolation - the second writer wins and the first "
      "writer's content vanishes silently. The classical Lost Update anomaly."),

    Paragraph("Problem 2 - Dropped Clerk webhook leaves users in a divergent state", H2),
    P("Clerk delivers a subscription cancellation as a fire-and-forget HTTPS POST. The "
      "naive handler treats each POST as a one-shot command: parse, mutate the user row, "
      "return 200. There is no idempotency table keyed on the <code>svix_id</code>, no "
      "outbox/inbox pattern, and no retry queue. If a network blip drops the TCP segment "
      "carrying the webhook (or our app crashes mid-request), Clerk's delivery is lost "
      "from our side and our row never transitions from <i>premium</i> to <i>free</i>. "
      "Worse, even when Clerk retries it (and it does), the naive handler would re-apply "
      "the mutation against any later state change, so retries are unsafe and were disabled. "
      "The two systems coordinate over an unreliable channel without an end-to-end "
      "consensus mechanism, so a single dropped event = permanent state inconsistency."),

    Paragraph("Problem 3 - Synchronous LLM call is a single point of failure", H2),
    P("The LLM call is awaited inline inside the request handler with no timeout, no "
      "retry budget, and no bulkhead. When the upstream takes 60 seconds to time out at "
      "the TCP level, every in-flight request to that endpoint holds onto a worker / "
      "event-loop task for 60 seconds. Uvicorn's worker pool is finite, so once enough "
      "requests stack up, new requests for unrelated endpoints (like serving the React "
      "app) also queue. One unhealthy dependency cascades into total unavailability - the "
      "textbook definition of a SPOF made worse by tight coupling."),
]

# --- Part 2 ---------------------------------------------------------------
story += [
    Spacer(1, 0.15*cm),
    Paragraph("Part 2 - Design: making each failure mode survivable", H1),

    Paragraph("Sync - Optimistic locking with monotonic version", H2),
    P("Add a <code>version INT</code> column to every editable row. Clients GET the row "
      "with its version, send it back as part of the update payload, and the server runs "
      "<code>UPDATE ... SET content=?, version=version+1 WHERE id=? AND version=?</code>. "
      "Postgres returns 0 rows affected when the predicate fails; we translate that into "
      "<b>409 Conflict</b> with the current version embedded. The client refetches, "
      "performs a 3-way merge in the UI, and retries. For richer collaborative editing we "
      "could layer Operational Transformation or CRDTs over this, but for a study-doc app "
      "the OCC-with-merge-on-conflict approach is cheap, drift-free, and gives the user "
      "visible feedback rather than silent data loss."),

    KeepTogether([Paragraph("Sequence diagram - two concurrent writers under OCC", H2),
                  sequence_diagram()]),

    Paragraph("Coordination - Idempotent webhook handler with retry queue and DLQ", H2),
    P("Treat the webhook as an at-least-once delivery channel. (1) Verify Clerk's svix "
      "signature, (2) look up <code>svix_id</code> in a processed-events table; if present, "
      "return the original 200 immediately - this makes retries safe. (3) Apply the state "
      "change inside the same transaction that inserts the idempotency row, so either both "
      "happen or neither does. (4) If the handler raises, push the event onto a retry queue "
      "(Redis Streams or Postgres-based) with exponential backoff: 2s, 4s, 8s. (5) After "
      "<code>MAX_RETRIES</code> the event lands in a dead-letter queue for human triage "
      "instead of being silently dropped. A periodic reconciliation job can also pull "
      "current subscription state from the Clerk API and re-apply missed transitions - the "
      "belt-and-braces guarantee that we eventually converge even if a webhook is lost "
      "forever."),

    Paragraph("Fault tolerance - Circuit breaker + bounded timeout + fallback", H2),
    P("Wrap the LLM call in a state machine: <b>CLOSED</b> forwards the call with a 1s "
      "timeout and counts failures; once <i>failure_threshold</i> consecutive failures "
      "trip it to <b>OPEN</b>, every subsequent call returns a cached/canned fallback in "
      "microseconds without touching the upstream. After <i>reset_after</i> seconds the "
      "breaker enters <b>HALF_OPEN</b> and lets one probe through; success closes the "
      "circuit, another failure re-opens it. This bounds the blast radius of an "
      "upstream outage from 'whole app hangs' to 'AI summaries return a graceful message'. "
      "Layered on top, a per-route asyncio.Semaphore (bulkhead) prevents the LLM endpoint "
      "from monopolising worker slots even before the breaker trips."),

    Paragraph("CAP trade-offs", H2),
    P("Each fix picks a different point on the CAP/PACELC surface. <b>Sync (Problem 1)</b> "
      "chooses <i>Consistency over Availability</i>: we deliberately reject the stale "
      "writer with 409 instead of accepting both writes and merging silently - correctness "
      "of shared documents is non-negotiable. <b>Webhooks (Problem 2)</b> are inherently "
      "<i>eventually consistent</i>: we accept brief divergence between Clerk and our DB "
      "in exchange for at-least-once delivery and idempotent application - the system "
      "converges, just not instantaneously. <b>LLM (Problem 3)</b> chooses "
      "<i>Availability and bounded Latency over Consistency</i> with the upstream: we'd "
      "rather serve a slightly stale or canned response than block the user for 60 seconds. "
      "PACELC-wise: when the LLM partition heals, we still prefer latency over a strongly "
      "consistent freshness guarantee, so the breaker's half-open probe is the only call "
      "that pays the full upstream latency cost during recovery."),
]

doc.build(story)
print(f"wrote {OUT}")
