import smtplib
import ssl

from daily_briefing.mailer import SmtpSettings, build_message, factory_for, send


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host, port, timeout, context=None):
        self.host, self.port, self.timeout, self.context = host, port, timeout, context
        self.calls: list[tuple] = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.starttls_context = context
        self.calls.append(("starttls",))

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, msg):
        self.calls.append(("send", msg["Subject"]))


def message():
    return build_message(subject="Hi", text="# Hi", html="<p>Hi</p>", sender="a@x", to="b@x")


def test_build_message_is_multipart():
    msg = message()
    assert (msg["Subject"], msg["From"], msg["To"]) == ("Hi", "a@x", "b@x")
    assert msg.get_body(("plain",)).get_content().strip() == "# Hi"
    assert "<p>Hi</p>" in msg.get_body(("html",)).get_content()


def test_factory_for_port():
    assert factory_for(465) is smtplib.SMTP_SSL
    assert factory_for(587) is smtplib.SMTP


def test_send_implicit_tls_strips_password_spaces():
    FakeSMTP.instances.clear()
    send(message(), SmtpSettings("smtp.gmail.com", 465, "a@x", "abcd efgh"), smtp_factory=FakeSMTP)
    smtp = FakeSMTP.instances[0]
    assert (smtp.host, smtp.port) == ("smtp.gmail.com", 465)
    assert smtp.calls == [("login", "a@x", "abcdefgh"), ("send", "Hi")]


def test_send_starttls_on_other_ports():
    FakeSMTP.instances.clear()
    send(message(), SmtpSettings("smtp.x", 587, "a@x", "pw"), smtp_factory=FakeSMTP)
    assert FakeSMTP.instances[0].calls[0] == ("starttls",)


def _verifies(ctx):
    return (
        isinstance(ctx, ssl.SSLContext)
        and ctx.verify_mode == ssl.CERT_REQUIRED
        and ctx.check_hostname is True
    )


def test_send_verifies_certificates_on_465():
    FakeSMTP.instances.clear()
    send(message(), SmtpSettings("smtp.x", 465, "a@x", "pw"), smtp_factory=FakeSMTP)
    assert _verifies(FakeSMTP.instances[0].context)


def test_send_verifies_certificates_on_587():
    FakeSMTP.instances.clear()
    send(message(), SmtpSettings("smtp.x", 587, "a@x", "pw"), smtp_factory=FakeSMTP)
    assert _verifies(FakeSMTP.instances[0].starttls_context)


def test_default_factory_uses_verifying_context(monkeypatch):
    FakeSMTP.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    send(message(), SmtpSettings("smtp.x", 465, "a@x", "pw"), smtp_factory=None)
    assert _verifies(FakeSMTP.instances[0].context)


def test_default_factory_starttls_path_matches_smtplib_signature(monkeypatch):
    class StrictSMTP(FakeSMTP):
        def __init__(self, host, port, timeout):  # real smtplib.SMTP has no context kwarg
            super().__init__(host, port, timeout)

    FakeSMTP.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP", StrictSMTP)
    send(message(), SmtpSettings("smtp.x", 587, "a@x", "pw"), smtp_factory=None)
    assert _verifies(FakeSMTP.instances[0].starttls_context)


def test_custom_provider_password_spaces_are_preserved():
    FakeSMTP.instances.clear()
    send(message(), SmtpSettings("smtp.example.com", 465, "a@x", " a b "), smtp_factory=FakeSMTP)
    assert FakeSMTP.instances[0].calls[0] == ("login", "a@x", " a b ")


def test_config_to_custom_smtp_preserves_exact_password():
    from daily_briefing.config import Config

    cfg = Config.from_env(
        {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_USER": "a@x",
            "SMTP_PASSWORD": " leading middle trailing ",
            "BRIEFING_KEY": "k" * 32,
        }
    )
    FakeSMTP.instances.clear()
    send(
        message(),
        SmtpSettings(cfg.smtp_host, cfg.smtp_port, cfg.smtp_user, cfg.smtp_password),
        smtp_factory=FakeSMTP,
    )
    assert FakeSMTP.instances[0].calls[0] == ("login", "a@x", " leading middle trailing ")


def test_config_to_gmail_normalizes_only_at_smtp_boundary():
    from daily_briefing.config import Config

    cfg = Config.from_env(
        {"SMTP_USER": "a@x", "SMTP_PASSWORD": " abcd efgh ", "BRIEFING_KEY": "k" * 32}
    )
    assert cfg.smtp_password == " abcd efgh "
    FakeSMTP.instances.clear()
    send(
        message(),
        SmtpSettings(cfg.smtp_host, cfg.smtp_port, cfg.smtp_user, cfg.smtp_password),
        smtp_factory=FakeSMTP,
    )
    assert FakeSMTP.instances[0].calls[0] == ("login", "a@x", "abcdefgh")
