"""B-85: the non-English flag (PRD Section 9 / AC-05). Offline fixtures only. The thresholds in
wi/crawl/language.py were set from these fixtures' measurements, with margin on both sides."""
from wi.crawl.language import declared_language, site_language, text_language

ENGLISH = (
    "Acme helps small and growing businesses get paid faster. Our platform brings invoicing, "
    "payments and reconciliation together in one place, so your finance team can spend less time "
    "chasing receipts and more time on the work that matters. Thousands of companies around the "
    "world use Acme to send invoices, accept cards and bank transfers, and see exactly where their "
    "cash is at any moment. We started in 2015 with a simple idea: billing should not be the "
    "hardest part of running a business. Today we serve teams of every size, from freelancers to "
    "enterprises with offices in more than forty countries. Start a free trial in minutes, or talk "
    "to our sales team about a plan that fits how you work."
)
SPANISH = (
    "Acme ayuda a las pequeñas y medianas empresas a cobrar más rápido. Nuestra plataforma reúne "
    "la facturación, los pagos y la conciliación en un solo lugar, para que su equipo de finanzas "
    "dedique menos tiempo a perseguir recibos y más tiempo al trabajo que importa. Miles de "
    "empresas en todo el mundo usan Acme para enviar facturas, aceptar tarjetas y transferencias "
    "bancarias, y ver en todo momento dónde está su dinero. Empezamos en 2015 con una idea sencilla: "
    "la facturación no debería ser la parte más difícil de un negocio. Hoy trabajamos con equipos de "
    "todos los tamaños, desde autónomos hasta grandes empresas con oficinas en más de cuarenta países."
)
GERMAN = (
    "Acme hilft kleinen und wachsenden Unternehmen, schneller bezahlt zu werden. Unsere Plattform "
    "bringt Rechnungsstellung, Zahlungen und Abgleich an einem Ort zusammen, damit sich Ihr "
    "Finanzteam weniger mit Belegen und mehr mit der Arbeit beschäftigen kann, die zählt. Tausende "
    "Unternehmen auf der ganzen Welt nutzen Acme, um Rechnungen zu versenden, Karten und "
    "Überweisungen anzunehmen und jederzeit zu sehen, wo sich ihr Geld befindet. Wir haben 2015 mit "
    "einer einfachen Idee begonnen: Die Abrechnung sollte nicht der schwierigste Teil eines "
    "Unternehmens sein. Heute arbeiten wir mit Teams jeder Größe, von Selbstständigen bis zu "
    "Konzernen mit Büros in mehr als vierzig Ländern."
)
JAPANESE = (
    "Acmeは、中小企業や成長企業がより早く支払いを受けられるよう支援します。請求書の発行、決済、"
    "照合をひとつの場所にまとめることで、経理チームは領収書の確認に追われる時間を減らし、本当に"
    "大切な仕事に集中できます。世界中の何千もの企業がAcmeを使って請求書を送り、カードや銀行振込を"
    "受け付け、資金の状況をいつでも確認しています。私たちは2015年に、請求業務はビジネスで最も難しい"
    "部分であるべきではないというシンプルな考えから始まりました。現在は個人事業主から四十か国以上に"
    "拠点を持つ大企業まで、あらゆる規模のチームにサービスを提供しています。"
)
# English, but mostly plan names, prices and feature labels: few English function words.
ENGLISH_PRICING = (
    "Starter $0 per month. 1 user. 3 projects. 500 MB storage. Email support. "
    "Pro $12 per user per month. Unlimited projects. 100 GB storage. Custom domains. SSO. SAML. "
    "API access. Webhooks. Audit log. Priority support. "
    "Business $24 per user per month. Everything in Pro. 1 TB storage. SCIM provisioning. "
    "Advanced permissions. Data residency EU US. Uptime SLA 99.9%. Dedicated CSM. "
    "Enterprise Custom pricing. Volume discounts. On-premise deployment. HIPAA. SOC 2 Type II. "
    "ISO 27001. Annual billing. Invoicing. Purchase orders. Contact sales. Start free trial. "
    "Compare plans. FAQ. Billing. Refunds. Seats. Add-ons. Storage packs. Integrations Slack Jira "
    "GitHub GitLab Bitbucket Salesforce HubSpot Zapier Okta Azure AD Google Workspace."
)
# English developer page dominated by code.
ENGLISH_CODE = (
    "Quickstart. Install the SDK and create a client. "
    "pip install acme-sdk import acme client = acme.Client(api_key=KEY) "
    "invoice = client.invoices.create(customer_id=cus_123, amount=4200, currency=usd) "
    "print(invoice.id, invoice.status) for item in client.invoices.list(limit=10): print(item.id) "
    "curl https://api.acme.com/v1/invoices -H Authorization: Bearer KEY -d amount=4200 -d currency=usd "
    "Webhooks POST /v1/webhooks url events invoice.paid invoice.failed payment.refunded "
    "Responses 200 OK 400 Bad Request 401 Unauthorized 404 Not Found 429 Too Many Requests "
    "Pagination cursor limit starting_after ending_before Idempotency-Key header retries backoff"
)
TINY = "Acme. Log in. Sign up."


def test_fixture_measurements_sit_clear_of_the_thresholds():
    # The numbers the thresholds were chosen from; kept as a test so a later change is visible.
    en, es, de, ja = (text_language(t) for t in (ENGLISH, SPANISH, GERMAN, JAPANESE))
    assert en["guess"] == "en" and en["en_ratio"] >= 0.20 and en["other_ratio"] < 0.05
    assert es["guess"] == "non-en" and es["other_ratio"] >= 0.20 and es["en_ratio"] < 0.05
    assert de["guess"] == "non-en" and de["other_ratio"] >= 0.20 and de["en_ratio"] < 0.05
    assert ja["guess"] == "non-en" and ja["latin_ratio"] < 0.2


def test_english_product_lists_and_code_are_never_called_non_english():
    for text in (ENGLISH_PRICING, ENGLISH_CODE):
        assert text_language(text)["guess"] in ("en", "unknown")
        flag = site_language([text])
        assert flag["non_english"] is False


def test_too_little_text_is_unknown_and_not_flagged():
    flag = site_language([TINY], start_html='<html lang="fr"><body>Acme</body></html>')
    assert flag == {**flag, "site_language": "unknown", "non_english": False}


def test_spanish_site_reports_the_declared_code_and_german_without_one_reports_non_en():
    es = site_language([SPANISH], start_html='<html lang="es-MX"><body></body></html>')
    assert (es["site_language"], es["non_english"], es["site_language_source"]) == ("es", True, "text + html lang")
    de = site_language([GERMAN], start_html="<html><body></body></html>")
    assert (de["site_language"], de["non_english"], de["site_language_source"]) == ("non-en", True, "text")
    ja = site_language([JAPANESE], start_html='<html lang="ja"><body></body></html>')
    assert (ja["site_language"], ja["non_english"]) == ("ja", True)


def test_a_wrong_html_lang_does_not_override_the_text():
    # Declared Spanish, actually English: the text decides, and nothing is flagged.
    en = site_language([ENGLISH], start_html='<html lang="es"><body></body></html>')
    assert (en["site_language"], en["non_english"]) == ("en", False)
    # Declared English, actually German: still flagged, reported as non-en (no non-English code).
    de = site_language([GERMAN], start_html='<html lang="en"><body></body></html>')
    assert (de["site_language"], de["non_english"]) == ("non-en", True)


def test_mixed_language_site_is_weighted_by_text_length():
    # Mostly English with one Spanish page: English. Mostly Spanish: flagged.
    assert site_language([ENGLISH, ENGLISH, ENGLISH, SPANISH])["non_english"] is False
    assert site_language([SPANISH, SPANISH, SPANISH, ENGLISH])["non_english"] is True
    # An even split is not a clear majority: not flagged.
    assert site_language([SPANISH, ENGLISH])["non_english"] is False


def test_declared_language_reads_the_primary_code():
    assert declared_language('<html lang="es-MX"><body></body></html>') == "es"
    assert declared_language('<html lang="EN_us"><body></body></html>') == "en"
    assert declared_language("<html><body></body></html>") is None
    assert declared_language(None) is None
