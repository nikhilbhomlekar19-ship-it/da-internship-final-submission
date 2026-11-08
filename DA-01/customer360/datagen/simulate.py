"""Synthetic world simulator.

People -> devices -> marketing journeys -> orders, rendered into the *same shapes the real sources have*:

  * GA4 BigQuery export schema (nested event_params, traffic_source, ecommerce ...)   -> raw ga4_events (local demo)
  * Segment warehouse tables (identifies, tracks, order_completed)                    -> raw segment_*
  * CRM (customers with messy emails/phones + duplicates, orders)                     -> raw crm_*
  * Ad-platform daily spend / clicks / platform-reported conversions                  -> raw ads_spend_daily
  * Ground truth (who is who, which sessions belong to whom, true response curves)   -> truth_* (evaluation only)

Order history follows the BG/NBD generative story (Fader, Hardie & Lee 2005) so the CLV model can be validated.
"""
from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

from .. import config as cfg
from .catalog import CAMPAIGNS, PAID, Campaign

EPOCH = datetime(1970, 1, 1)
WIN_START = datetime.combine(cfg.START_DATE, datetime.min.time())
WIN_END = datetime.combine(cfg.END_DATE, datetime.min.time()) + timedelta(days=1) - timedelta(seconds=1)
HIST_START = datetime.combine(cfg.HISTORY_START, datetime.min.time())
DAYS = [cfg.START_DATE + timedelta(days=i) for i in range((cfg.END_DATE - cfg.START_DATE).days + 1)]
N_DAYS, N_CAMP = len(DAYS), len(CAMPAIGNS)
BGNBD_TRUE = dict(r=0.9, alpha=18.0, a=0.9, b=3.0)  # weeks; ground truth for the CLV model

COUNTRY_NAME = {"US": "United States", "CA": "Canada", "GB": "United Kingdom", "IN": "India", "AU": "Australia"}
GEO = {
    "US": [("California", "Los Angeles"), ("California", "San Francisco"), ("New York", "New York"), ("Texas", "Austin"),
           ("Illinois", "Chicago"), ("Washington", "Seattle"), ("Florida", "Miami"), ("Massachusetts", "Boston")],
    "CA": [("Ontario", "Toronto"), ("British Columbia", "Vancouver"), ("Quebec", "Montreal")],
    "GB": [("England", "London"), ("England", "Manchester"), ("Scotland", "Edinburgh")],
    "IN": [("Maharashtra", "Pune"), ("Karnataka", "Bengaluru"), ("Delhi", "New Delhi")],
    "AU": [("New South Wales", "Sydney"), ("Victoria", "Melbourne")],
}
SITE = "https://shop.example.com"
PATHS = ["/", "/c/hoodies", "/c/tees", "/c/drinkware", "/c/stationery", "/c/bags", "/sale", "/new-arrivals"]


# ----------------------------------------------------------------------------- small helpers
def micros(dt: datetime) -> int:
    return (dt - EPOCH) // timedelta(microseconds=1)


def epoch_s(dt: datetime) -> int:
    return int((dt - EPOCH).total_seconds())


def season(d: date) -> float:
    if date(2020, 11, 23) <= d <= date(2020, 11, 30):
        return 1.7  # Black Friday / Cyber Monday
    if date(2020, 12, 1) <= d <= date(2020, 12, 14):
        return 1.25
    if date(2020, 12, 15) <= d <= date(2020, 12, 22):
        return 1.15
    if date(2020, 12, 23) <= d <= date(2021, 1, 1):
        return 0.8
    if date(2021, 1, 2) <= d <= date(2021, 1, 6):
        return 1.1  # New-year sale
    return 1.0


def weekday_factor(d: date) -> float:
    return [1.0, 1.0, 0.98, 0.97, 0.92, 0.85, 0.95][d.weekday()]


HOUR_P = np.array([1, 1, 1, .6, .5, .6, 1, 2, 3, 4, 4.5, 5, 5, 5, 5, 5, 5, 5.5, 6, 7, 7.5, 7, 5, 3], float)
HOUR_P /= HOUR_P.sum()
DAY_P = np.array([season(d) * weekday_factor(d) for d in DAYS], float)
DAY_P /= DAY_P.sum()
SENS = {"Paid Search": 1.0, "Paid Social": 1.0, "Display": 0.8, "Affiliate": 1.2, "Email": 1.0, "App Push": 0.8,
        "Organic Search": 0.6, "Organic Social": 0.6, "Referral": 0.5, "Direct": 0.7}


def _norm(a) -> np.ndarray:
    a = np.asarray(a, float)
    return a / a.sum()


STAGE_W = {k: _norm([getattr(c, k) for c in CAMPAIGNS]) for k in ("disc", "mid", "close", "vol")}
STAGE_W["single"] = _norm(0.5 * STAGE_W["close"] + 0.5 * STAGE_W["disc"])
MASK_NOT_CRM = np.array([0.0 if c.crm_only else 1.0 for c in CAMPAIGNS])
MASK_NOT_APP = np.array([0.0 if c.app_only else 1.0 for c in CAMPAIGNS])


def day_idx(dt: datetime) -> int:
    return int(min(max((dt.date() - cfg.START_DATE).days, 0), N_DAYS - 1))


# ----------------------------------------------------------------------------- entities
@dataclass(eq=False)
class Browser:
    ga_id: str
    ajs_id: str
    category: str
    os: str
    browser: str
    geo: tuple = ("United States", "California", "Los Angeles")
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    n_before: int = 0
    first_touch: datetime | None = None
    first_cmp: Campaign | None = None


@dataclass(eq=False)
class Person:
    pid: str
    is_crm: bool
    is_existing: bool = False
    is_buyer: bool = False
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    login_email: str = ""
    phone: str | None = None
    country: str = "US"
    region: str = ""
    city: str = ""
    signup_ts: datetime | None = None
    app_user: bool = False
    app_id: str | None = None
    app_os: str = "iOS"
    consent: bool = True
    seg_web: bool = True
    ga_uid_on: bool = False
    newsletter_pre: bool = False
    browsers: list = field(default_factory=list)
    crm_ids: list = field(default_factory=list)  # [(crm_id, created_at, raw_email, raw_phone)]
    dup_kind: str | None = None
    order_ts: list = field(default_factory=list)
    opt_in: bool = True
    self_src: str | None = None
    signup_channel: str = "web_signup"
    app_login_ts: datetime | None = None
    spend_mult: float = 1.0  # customer-level spend propensity (gives the Gamma-Gamma model something to learn)


@dataclass(eq=False)
class Order:
    order_id: str
    person: Person
    ts: datetime
    channel: str  # web | app | store
    crm_id: str
    total: float
    discount: float
    status: str
    refund: float
    external_ref: str | None
    coupon: str | None
    items: int
    is_first: bool
    in_window: bool
    online_tracked: bool = False
    purchase_ts: datetime | None = None
    conv: "Sess | None" = None

    @property
    def net(self) -> float:
        return round(self.total - self.discount, 2)


@dataclass(eq=False)
class Sess:
    pid: str
    kind: str  # web | app
    device_id: str
    start: datetime
    cmp: Campaign
    browser: Browser | None = None
    person: Person | None = None
    order: Order | None = None
    protected: bool = False
    n_pages: int = 1
    cart: bool = False
    checkout: bool = False
    bounce: bool = False
    drop: bool = False
    seq: int = 0

    @property
    def key(self) -> str:
        return f"{self.device_id}.{epoch_s(self.start)}"


@dataclass
class SimResult:
    ga4_jsonl: Path
    tables: dict
    truth: dict
    summary: dict


# ----------------------------------------------------------------------------- simulator
class Simulator:
    def __init__(self, n_persons=6000, crm_rate=0.55, bounce_per_day=450, seed=42, target_mer=3.4, out_dir=None):
        self.n_persons, self.crm_rate, self.bounce_per_day = n_persons, crm_rate, bounce_per_day
        self.target_mer, self.seed = target_mer, seed
        self.rng = np.random.default_rng(seed)
        Faker.seed(seed)
        self.fake = Faker("en_US")
        self.out_dir = Path(out_dir or cfg.DATA_DIR / "raw")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.boost = np.stack(
            [np.array([season(d) for d in DAYS]) ** SENS[c.channel_group] * np.exp(self.rng.normal(0, 0.28, N_DAYS))
             for c in CAMPAIGNS]
        )
        self.persons: list[Person] = []
        self.orders: list[Order] = []
        self.sessions: list[Sess] = []
        self._n = {"order": 0, "crm": 0, "evt": 0, "txn": 0}
        self._emails: set[str] = set()

    # ---- id helpers
    def _next(self, k: str) -> int:
        self._n[k] += 1
        return self._n[k]

    def _uuid(self) -> str:
        return str(uuid.UUID(bytes=self.rng.bytes(16), version=4))

    # ---- sampling helpers
    def pick(self, stage: str, d_idx: int, crm_ok: bool, kind: str) -> Campaign:
        w = STAGE_W[stage] * self.boost[:, d_idx]
        if not crm_ok:
            w = w * MASK_NOT_CRM
        if kind != "app":
            w = w * MASK_NOT_APP
        return CAMPAIGNS[int(self.rng.choice(N_CAMP, p=w / w.sum()))]

    def rand_time(self, d: date) -> datetime:
        h = int(self.rng.choice(24, p=HOUR_P))
        return datetime(d.year, d.month, d.day, h, int(self.rng.integers(0, 60)), int(self.rng.integers(0, 60)))

    def new_browser(self, geo, category=None, valid_from=None, valid_to=None) -> Browser:
        rng = self.rng
        cat = category or str(rng.choice(["desktop", "mobile", "tablet"], p=[.50, .42, .08]))
        if cat == "desktop":
            os_ = str(rng.choice(["Windows", "Macintosh", "Linux"], p=[.55, .40, .05]))
            br = str(rng.choice(["Chrome", "Safari", "Edge", "Firefox"], p=[.65, .20, .10, .05]))
        else:
            os_ = str(rng.choice(["iOS", "Android"], p=[.55, .45]))
            br = "Safari" if os_ == "iOS" and rng.random() < .7 else "Chrome"
        ga = f"{int(rng.integers(10**9, 2 * 10**9))}.{int(rng.integers(1_500_000_000, 1_610_000_000))}"
        return Browser(ga, self._uuid(), cat, os_, br, geo, valid_from, valid_to)

    def pick_browser(self, p: Person, t: datetime) -> Browser:
        valid = [b for b in p.browsers if (b.valid_from is None or t >= b.valid_from) and (b.valid_to is None or t < b.valid_to)]
        valid = valid or p.browsers
        return valid[0] if len(valid) == 1 else valid[int(self.rng.integers(len(valid)))]

    # ---- people
    def _email(self, first: str, last: str, rng) -> tuple[str, str]:
        dom = str(rng.choice(["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com", "proton.me", "aol.com", "work"],
                             p=[.45, .14, .12, .07, .08, .04, .03, .07]))
        if dom == "work":
            dom = str(rng.choice(["acme-corp.com", "northwind.io", "globex.net", "initech.com"]))
        base = "".join(ch for ch in f"{first}.{last}".lower() if ch.isalnum() or ch == ".")
        local = base
        if dom == "gmail.com" and rng.random() < .15 and len(first) > 3:
            local = base[:2] + "." + base[2:]  # dotted gmail variant
        n = 0
        while f"{local}{'' if n == 0 else n}@{dom}" in self._emails:
            n += 1
        email = f"{local}{'' if n == 0 else n}@{dom}"
        self._emails.add(email)
        return email, dom

    @staticmethod
    def messy_email(email: str, rng) -> str:
        local, dom = email.split("@")
        r = rng.random()
        if r < .74:
            return email
        if r < .86:
            return f"{local.capitalize()}@{dom}"
        if r < .93:
            return email.upper()
        if r < .97:
            return email + " "
        return f"{local}+promo@{dom}"

    @staticmethod
    def messy_phone(digits: str, rng) -> str:
        fmt = int(rng.integers(5))
        a, b, c = digits[:3], digits[3:6], digits[6:]
        return [f"({a}) {b}-{c}", f"{a}-{b}-{c}", f"+1 {a} {b} {c}", f"{a}.{b}.{c}", f"1{digits}"][fmt]

    def make_person(self, i: int, is_crm: bool) -> Person:
        rng, fake = self.rng, self.fake
        p = Person(pid=f"p{i:06d}", is_crm=is_crm)
        cc = str(rng.choice(list(COUNTRY_NAME), p=[.70, .09, .09, .06, .06]))
        p.country = cc
        p.region, p.city = GEO[cc][int(rng.integers(len(GEO[cc])))]
        geo = (COUNTRY_NAME[cc], p.region, p.city)
        if is_crm:
            p.first_name, p.last_name = fake.first_name(), fake.last_name()
            p.email, dom = self._email(p.first_name, p.last_name, rng)
            local = p.email.split("@")[0]
            p.login_email = f"{local.replace('.', '')}@{dom}" if dom == "gmail.com" and rng.random() < .2 else p.email
            p.phone = "".join(str(int(x)) for x in rng.integers(0, 10, 10)) if rng.random() < .8 else None
            if p.phone:
                p.phone = str(int(rng.integers(2, 10))) + p.phone[1:]
            p.is_existing = bool(rng.random() < .45)
            p.spend_mult = float(rng.lognormal(0, .45))
            p.is_buyer = bool(rng.random() < (.85 if p.is_existing else .70))
            p.app_user = bool(rng.random() < .28)
            if p.app_user:
                p.app_id, p.app_os = self._uuid(), str(rng.choice(["iOS", "Android"], p=[.55, .45]))
            p.consent = bool(rng.random() > .06)
            p.seg_web = bool(rng.random() < .85)
            p.ga_uid_on = bool(rng.random() < .5)
            p.opt_in = bool(rng.random() < .72)
            p.self_src = str(rng.choice(["Google", "Friend", "Instagram", "TikTok", "Email", "Other", "none"],
                                        p=[.28, .17, .15, .08, .05, .07, .20]))
            p.self_src = None if p.self_src == "none" else p.self_src
            scen = rng.random()
            if scen < .68:
                p.browsers = [self.new_browser(geo)]
            elif scen < .90:
                b1 = self.new_browser(geo)
                b2 = self.new_browser(geo, category="mobile" if b1.category == "desktop" else "desktop")
                p.browsers = [b1, b2]
            else:  # cookie reset mid-window
                reset = WIN_START + timedelta(days=float(rng.uniform(10, 80)))
                b1 = self.new_browser(geo, valid_to=reset)
                b2 = self.new_browser(geo, category=b1.category, valid_from=reset)
                p.browsers = [b1, b2]
        else:
            p.browsers = [self.new_browser(geo)]
        return p

    # ---- orders
    def plan_orders(self, p: Person) -> None:
        rng = self.rng
        if not p.is_buyer:
            return
        r, alpha, a, b = (BGNBD_TRUE[k] for k in ("r", "alpha", "a", "b"))
        lam = max(float(rng.gamma(r, 1.0 / alpha)), 1e-4)  # purchases per week while alive
        pdrop = float(rng.beta(a, b))  # P(drop out) after each purchase
        if p.is_existing:
            span = (WIN_START - timedelta(days=10) - HIST_START).total_seconds()
            t0 = HIST_START + timedelta(seconds=float(rng.uniform(0, span)))
        else:
            t0 = self.rand_time(DAYS[int(rng.choice(N_DAYS, p=DAY_P))])
        t0 = t0.replace(microsecond=0)
        times, t = [t0], t0
        while True:  # BG/NBD: the customer may drop out only AFTER a repeat purchase
            t = t + timedelta(weeks=min(float(rng.exponential(1.0 / lam)), 600))
            if t > WIN_END:
                break
            times.append(t)
            if rng.random() < pdrop:
                break
        out, prev = [], None
        for t in sorted(t.replace(microsecond=0) for t in times):
            if WIN_START <= t < WIN_START + timedelta(hours=1):
                t = WIN_START + timedelta(hours=1)
            if prev is not None and t - prev < timedelta(hours=3):
                t = prev + timedelta(hours=3)
            if t > WIN_END:
                break
            out.append(t)
            prev = t
        p.order_ts = out

    def assign_crm(self, p: Person) -> None:
        """Signup time, CRM record(s) incl. duplicates (same person, two records)."""
        rng = self.rng
        first = p.order_ts[0] if p.order_ts else None
        if p.is_buyer and first is not None:
            if p.is_existing:
                p.signup_ts = first - timedelta(minutes=float(rng.uniform(2, 60 * 24 * 10)))
            elif rng.random() < .35:
                p.newsletter_pre = True
                p.signup_ts = max(WIN_START, first - timedelta(days=float(rng.uniform(1, 20))))
            else:
                p.signup_ts = first - timedelta(minutes=float(rng.uniform(2, 10)))
        elif p.is_existing:
            p.signup_ts = HIST_START + timedelta(days=float(rng.uniform(0, 360)))
        else:
            p.signup_ts = self.rand_time(DAYS[int(rng.choice(N_DAYS, p=DAY_P))])
        p.signup_channel = ("app_signup" if p.app_user and rng.random() < .4 else
                            ("guest_checkout" if (not p.is_existing and not p.newsletter_pre and p.is_buyer and rng.random() < .5)
                             else ("store" if p.is_existing and rng.random() < .1 else "web_signup")))
        raw_phone = self.messy_phone(p.phone, rng) if p.phone else None
        p.crm_ids = [(f"C{self._next('crm'):06d}", p.signup_ts, self.messy_email(p.email, rng), raw_phone)]
        if p.order_ts and rng.random() < .045:  # duplicate CRM record
            kind = "phone_only" if (p.phone and rng.random() < .4) else "email_variant"
            created = p.order_ts[0] + timedelta(days=float(rng.uniform(1, 120)))
            if created <= WIN_END:
                if kind == "email_variant":
                    local, dom = p.email.split("@")
                    raw = [f"{local.upper()}@{dom}", f"{local}+shop@{dom}", f"{local.capitalize()}@{dom.upper()}"][int(rng.integers(3))]
                else:
                    raw = f"{p.first_name}{p.last_name}@{rng.choice(['acme-corp.com', 'northwind.io', 'globex.net'])}".lower()
                p.dup_kind = kind
                p.crm_ids.append((f"C{self._next('crm'):06d}", created, raw, self.messy_phone(p.phone, rng) if p.phone else None))

    def crm_id_at(self, p: Person, ts: datetime) -> str:
        if len(p.crm_ids) > 1 and ts >= p.crm_ids[1][1] and self.rng.random() < .55:
            return p.crm_ids[1][0]
        return p.crm_ids[0][0]

    def materialize_orders(self, p: Person) -> None:
        rng = self.rng
        for idx, ts in enumerate(p.order_ts):
            in_window = ts >= WIN_START
            ch = "web"
            if idx > 0 and p.is_existing and rng.random() < .06:
                ch = "store"
            elif p.app_user and rng.random() < .65:
                ch = "app"
            total = float(np.clip(round(float(rng.lognormal(math.log(40), .35)) * p.spend_mult + 4, 2), 9, 450))
            u = rng.random()
            status = "completed" if u < .91 else ("returned" if u < .98 else "cancelled")
            n = self._next("order")
            o = Order(order_id=f"O{n:07d}", person=p, ts=ts, channel=ch, crm_id=self.crm_id_at(p, ts), total=total,
                      discount=0.0, status=status, refund=0.0,
                      external_ref=None if ch == "store" else f"{'T' if ch == 'web' else 'A'}{n:08d}",
                      coupon=None, items=max(1, int(round(total / 30 + rng.normal(0, .5)))), is_first=(idx == 0), in_window=in_window)
            if in_window and ch != "store":
                self.build_journey(o)
            disc_p = .7 if (o.conv is not None and o.conv.cmp.key in ("aff_coupon", "email_promo")) else .22
            if rng.random() < disc_p:
                o.discount = round(total * float(rng.choice([.10, .15, .20, .25])), 2)
                o.coupon = f"SAVE{int(round(o.discount / total * 100))}"
            net = round(total - o.discount, 2)
            o.refund = round(net * (1.0 if (status == "cancelled" or rng.random() < .7) else .5), 2) if status != "completed" else 0.0
            self.orders.append(o)

    # ---- journeys & sessions
    def _session(self, p: Person, st: datetime, stage: str, kind: str, protected=False, order=None, final=False) -> Sess | None:
        rng = self.rng
        if kind == "web" and not p.consent:
            return None  # no GA4 consent -> invisible to analytics
        crm_ok = bool(p.is_crm and p.signup_ts is not None and st >= p.signup_ts)
        cmp = self.pick(stage, day_idx(st), crm_ok, kind)
        b = self.pick_browser(p, st) if kind == "web" else None
        did = b.ga_id if b else p.app_id
        n_pages = min(3 + int(rng.geometric(.4)), 12) if final else min(1 + int(rng.geometric(.45)), 8)
        return Sess(p.pid, kind, did, st, cmp, b, p, order, protected, n_pages,
                    cart=final or rng.random() < .10, checkout=final or rng.random() < .04)

    def build_journey(self, o: Order) -> None:
        rng, p = self.rng, o.person
        o.purchase_ts = o.ts - timedelta(seconds=int(rng.integers(5, 90)))
        conv_start = o.purchase_ts - timedelta(minutes=float(rng.uniform(2, 25)))
        n = min(1 + int(rng.poisson(2.2 if o.is_first else .9)), 8)
        starts, t = [conv_start], conv_start
        for _ in range(n - 1):
            t = t - timedelta(hours=6 + float(rng.exponential(60)))
            starts.append(t)
        starts.reverse()
        for k, st in enumerate(starts):
            last = k == n - 1
            if st < WIN_START:
                continue  # before tracking began (left-censored journey)
            if n == 1:
                stage = "close" if p.is_existing else "single"
            elif last:
                stage = "close"
            elif k == 0:
                stage = "mid" if p.is_existing else "disc"
            else:
                stage = "mid"
            kind = o.channel if last else ("app" if (p.app_user and rng.random() < .55) else "web")
            s = self._session(p, st, stage, kind, protected=True, order=o if last else None, final=last)
            if s is None:
                continue
            self.sessions.append(s)
            if last:
                o.conv, o.online_tracked = s, True

    def browse_sessions(self, p: Person) -> None:
        rng = self.rng
        start = max(WIN_START, p.signup_ts or WIN_START)
        span = max((WIN_END - start).days, 1)
        n = int(rng.poisson((1.3 if p.is_existing else .8) / 30 * span))
        for _ in range(n):
            d = DAYS[int(rng.choice(N_DAYS, p=DAY_P))]
            st = self.rand_time(d)
            if st < start:
                continue
            kind = "app" if (p.app_user and rng.random() < .5) else "web"
            s = self._session(p, st, "mid" if p.is_existing else "disc", kind)
            if s:
                self.sessions.append(s)

    def anon_sessions(self, p: Person) -> None:
        rng = self.rng
        n = 1 + int(rng.poisson(1.2))
        for k in range(n):
            st = self.rand_time(DAYS[int(rng.choice(N_DAYS, p=DAY_P))])
            cmp = self.pick("vol" if k == 0 else "mid", day_idx(st), False, "web")
            b = p.browsers[0]
            self.sessions.append(Sess(p.pid, "web", b.ga_id, st, cmp, b, p, None, False, min(1 + int(rng.geometric(.5)), 8),
                                      cart=rng.random() < .08, checkout=rng.random() < .02))

    def bounce_sessions(self) -> None:
        rng = self.rng
        for di, d in enumerate(DAYS):
            n = int(round(self.bounce_per_day * season(d) * weekday_factor(d) * float(np.exp(rng.normal(0, .08)))))
            w = STAGE_W["vol"] * self.boost[:, di] * MASK_NOT_CRM * MASK_NOT_APP
            ks = rng.choice(N_CAMP, size=n, p=w / w.sum())
            hours = rng.choice(24, size=n, p=HOUR_P)
            for k, h in zip(ks, hours):
                st = datetime(d.year, d.month, d.day, int(h), int(rng.integers(0, 60)), int(rng.integers(0, 60)))
                cc = str(rng.choice(list(COUNTRY_NAME), p=[.70, .09, .09, .06, .06]))
                rg, ct = GEO[cc][int(rng.integers(len(GEO[cc])))]
                b = self.new_browser((COUNTRY_NAME[cc], rg, ct))
                self.sessions.append(Sess("bounce", "web", b.ga_id, st, CAMPAIGNS[int(k)], b, None, None, False, 1, bounce=True))

    def finalize_sessions(self) -> None:
        """Keep devices' sessions >= 45 min apart (so app sessionisation is unambiguous) and number them."""
        by_dev: dict[str, list[Sess]] = {}
        for s in self.sessions:
            by_dev.setdefault(s.device_id, []).append(s)
        for lst in by_dev.values():
            lst.sort(key=lambda s: s.start)
            last = None
            for s in lst:
                if last is not None and (s.start - last.start) < timedelta(minutes=45):
                    if s.protected and not last.protected:
                        last.drop = True
                    elif not s.protected:
                        s.drop = True
                        continue
                last = s
        self.sessions = [s for s in self.sessions if not s.drop]
        for o in self.orders:
            if o.conv is not None and o.conv.drop:
                o.conv, o.online_tracked = None, False
        by_dev = {}
        for s in sorted(self.sessions, key=lambda s: s.start):
            by_dev.setdefault(s.device_id, []).append(s)
        for lst in by_dev.values():
            b = lst[0].browser
            for i, s in enumerate(lst):
                s.seq = i
            if b is not None and b.first_cmp is None:
                b.first_cmp = lst[0].cmp
                b.first_touch = lst[0].start - (timedelta(days=float(self.rng.uniform(20, 300))) if (lst[0].person and lst[0].person.is_existing) else timedelta(0))
                b.n_before = int(self.rng.integers(2, 25)) if (lst[0].person and lst[0].person.is_existing) else 0
        for p in self.persons:  # app login time = first app session on/after signup
            if p.app_user and p.is_crm:
                apps = sorted((s.start for s in self.sessions if s.pid == p.pid and s.kind == "app" and s.start >= p.signup_ts - timedelta(minutes=30)))
                p.app_login_ts = apps[0] + timedelta(seconds=45) if apps else None

    # ---- renderers
    def _gp(self, key, s=None, i=None) -> dict:
        v = {}
        if s is not None:
            v["string_value"] = s
        if i is not None:
            v["int_value"] = int(i)
        return {"key": key, "value": v}

    def _page(self, s: Sess, first: bool) -> str:
        path = PATHS[int(self.rng.integers(len(PATHS)))]
        if first and s.cmp.key != "direct":
            return f"{SITE}{path}?utm_source={s.cmp.source}&utm_medium={s.cmp.medium}&utm_campaign={s.cmp.campaign}"
        return f"{SITE}{path}"

    def ga4_rows(self, s: Sess):
        rng, b, p = self.rng, s.browser, s.person
        c = s.cmp
        logged = bool(p and p.is_crm and p.ga_uid_on and s.start >= p.signup_ts and (s.order is not None or rng.random() < .7))
        uid = None
        if logged:
            uid = p.crm_ids[0][0] if (len(p.crm_ids) == 1 or s.start < p.crm_ids[1][1]) else p.crm_ids[int(rng.integers(2))][0]
        sid = epoch_s(s.start)
        fc = b.first_cmp or c
        ts_name = {"organic": "(organic)", "(none)": "(direct)", "referral": "(referral)"}.get(fc.medium, fc.campaign)
        base = {
            "user_id": uid, "user_pseudo_id": b.ga_id, "user_first_touch_timestamp": micros(b.first_touch or s.start),
            "device": {"category": b.category, "operating_system": b.os, "web_info": {"browser": b.browser}},
            "geo": {"country": b.geo[0], "region": b.geo[1], "city": b.geo[2]},
            "traffic_source": {"name": ts_name, "medium": fc.medium, "source": fc.source},
            "platform": "WEB", "stream_id": "2100450278",
        }
        sess_params = [self._gp("ga_session_id", i=sid), self._gp("ga_session_number", i=b.n_before + s.seq + 1)]
        utm = [self._gp("source", s=c.source), self._gp("medium", s=c.medium), self._gp("campaign", s=c.campaign)]
        names = [("session_start", utm)]
        if s.seq == 0 and b.n_before == 0:
            names.insert(0, ("first_visit", []))
        for i in range(s.n_pages):
            names.append(("page_view", [self._gp("page_location", s=self._page(s, i == 0)),
                                        self._gp("engagement_time_msec", i=int(rng.integers(1500, 60000)))] + (utm if i == 0 else [])))
            if rng.random() < .5:
                names.append(("view_item", [self._gp("page_location", s=f"{SITE}/p/{int(rng.integers(1000, 9999))}")]))
        if s.cart:
            names.append(("add_to_cart", []))
        if s.checkout:
            names.append(("begin_checkout", []))
        o = s.order
        has_purchase = o is not None and o.channel == "web" and o.online_tracked
        end = o.purchase_ts if has_purchase else s.start + timedelta(seconds=float(rng.uniform(20, 90)) * s.n_pages)
        m = len(names)
        fr = np.sort(rng.uniform(0, 1, m)) if m > 1 else np.array([0.0])
        fr[0] = 0.0
        total = (end - s.start).total_seconds()
        for k, (name, prm) in enumerate(names):
            t = s.start + timedelta(seconds=float(total * fr[k] * (0.97 if has_purchase else 1.0)))
            yield {**base, "event_date": t.strftime("%Y%m%d"), "event_timestamp": micros(t), "event_name": name,
                   "event_params": sess_params + prm, "ecommerce": None}
        if has_purchase:
            rev = o.net if rng.random() > .03 else round(o.net + float(rng.choice([-4.99, 4.99, 6.5])), 2)
            ev = {**base, "event_date": o.purchase_ts.strftime("%Y%m%d"), "event_timestamp": micros(o.purchase_ts),
                  "event_name": "purchase", "event_params": sess_params,
                  "ecommerce": {"total_item_quantity": o.items, "purchase_revenue_in_usd": rev, "purchase_revenue": rev,
                                "unique_items": o.items, "transaction_id": o.external_ref}}
            yield ev
            if rng.random() < .02:  # double-fired purchase tag (classic GA4 gotcha)
                yield dict(ev)

    def write_ga4(self) -> Path:
        path = self.out_dir / "ga4_events.jsonl"
        n = 0
        with open(path, "w") as fh:
            for s in self.sessions:
                if s.kind != "web":
                    continue
                for r in self.ga4_rows(s):
                    fh.write(json.dumps(r, separators=(",", ":")) + "\n")
                    n += 1
        self.n_ga4_events = n
        return path

    def render_segment(self, web_identifies: bool = True):
        rng = self.rng
        ident, tracks, orders = [], [], []

        def eid():
            return f"msg-{self._next('evt'):09d}"

        for p in self.persons:  # identify: app login + web logins
            if not p.is_crm:
                continue
            cid = p.crm_ids[0][0]
            if p.app_login_ts is not None:
                lib = "analytics-ios" if p.app_os == "iOS" else "analytics-android"
                ident.append({"id": eid(), "anonymous_id": p.app_id, "user_id": cid, "timestamp": p.app_login_ts,
                              "received_at": p.app_login_ts + timedelta(seconds=1), "email": p.login_email, "ga_client_id": None,
                              "context_library_name": lib})
        seen = set()
        for s in sorted((s for s in self.sessions if web_identifies and s.kind == "web" and s.person is not None and s.person.is_crm and s.person.seg_web),
                        key=lambda s: s.start):
            p = s.person
            if s.start < p.signup_ts - timedelta(minutes=30) or (p.pid, s.browser.ga_id) in seen:
                continue
            if s.order is not None or rng.random() < .75:
                seen.add((p.pid, s.browser.ga_id))
                t = s.start + timedelta(seconds=60)
                cid = p.crm_ids[0][0] if (len(p.crm_ids) == 1 or t < p.crm_ids[1][1]) else p.crm_ids[int(rng.integers(2))][0]
                ident.append({"id": eid(), "anonymous_id": s.browser.ajs_id, "user_id": cid, "timestamp": t,
                              "received_at": t + timedelta(seconds=1), "email": p.login_email, "ga_client_id": s.browser.ga_id,
                              "context_library_name": "analytics.js"})
        for s in self.sessions:
            if s.kind != "app":
                continue
            p, c, o = s.person, s.cmp, s.order
            names = ["Application Opened"] + ["Product Viewed"] * max(1, s.n_pages - 1)
            if s.cart:
                names.append("Product Added")
            if s.checkout:
                names.append("Checkout Started")
            has_order = o is not None and o.channel == "app"
            end = o.purchase_ts if has_order else s.start + timedelta(seconds=float(rng.uniform(15, 60)) * s.n_pages)
            total = (end - s.start).total_seconds()
            m = len(names)
            fr = np.sort(rng.uniform(0, 1, m)) if m > 1 else np.array([0.0])
            fr[0] = 0.0
            campaign_ctx = (c.source, c.medium, c.campaign) if c.key != "direct" else (None, None, None)
            seq = [(n_, s.start + timedelta(seconds=float(total * fr[k] * (0.97 if has_order else 1.0)))) for k, n_ in enumerate(names)]
            if has_order:
                seq.append(("Order Completed", o.purchase_ts))
            for k, (name, t) in enumerate(seq):
                uid = p.crm_ids[0][0] if (p is not None and p.app_login_ts is not None and t >= p.app_login_ts) else None
                tracks.append({"id": eid(), "anonymous_id": s.device_id, "user_id": uid, "event": name, "event_text": name, "timestamp": t,
                               "received_at": t + timedelta(seconds=1),
                               "context_campaign_source": campaign_ctx[0] if k == 0 else None,
                               "context_campaign_medium": campaign_ctx[1] if k == 0 else None,
                               "context_campaign_name": campaign_ctx[2] if k == 0 else None,
                               "context_device_type": "ios" if p.app_os == "iOS" else "android",
                               "context_os_name": p.app_os, "context_library_name": "analytics-ios" if p.app_os == "iOS" else "analytics-android"})
            if has_order:
                uid = p.crm_ids[0][0] if (p.app_login_ts is not None and o.purchase_ts >= p.app_login_ts) else None
                orders.append({"id": eid(), "anonymous_id": s.device_id, "user_id": uid, "timestamp": o.purchase_ts,
                               "order_id": o.external_ref, "total": o.total, "revenue": o.net, "currency": "USD", "coupon": o.coupon,
                               "context_campaign_source": campaign_ctx[0], "context_campaign_medium": campaign_ctx[1],
                               "context_campaign_name": campaign_ctx[2]})
        cols_t = ["id", "anonymous_id", "user_id", "event", "event_text", "timestamp", "received_at", "context_campaign_source",
                  "context_campaign_medium", "context_campaign_name", "context_device_type", "context_os_name", "context_library_name"]
        cols_o = ["id", "anonymous_id", "user_id", "timestamp", "order_id", "total", "revenue", "currency", "coupon",
                  "context_campaign_source", "context_campaign_medium", "context_campaign_name"]
        cols_i = ["id", "anonymous_id", "user_id", "timestamp", "received_at", "email", "ga_client_id", "context_library_name"]
        return (pd.DataFrame(ident, columns=cols_i), pd.DataFrame(tracks, columns=cols_t), pd.DataFrame(orders, columns=cols_o))

    def render_crm(self):
        rows, n_orders = [], {}
        for o in self.orders:
            if o.status == "completed":
                n_orders[o.person.pid] = n_orders.get(o.person.pid, 0) + 1
        for p in self.persons:
            if not p.is_crm:
                continue
            k = n_orders.get(p.pid, 0)
            tier = "gold" if k >= 4 else ("silver" if k >= 2 else "none")
            for cid, created, raw_email, raw_phone in p.crm_ids:
                rows.append({"customer_id": cid, "first_name": p.first_name, "last_name": p.last_name, "email": raw_email,
                             "phone": raw_phone, "country": p.country, "city": p.city, "created_at": created,
                             "marketing_opt_in": p.opt_in, "loyalty_tier": tier, "self_reported_source": p.self_src,
                             "signup_channel": p.signup_channel, "updated_at": min(WIN_END, created + timedelta(days=float(self.rng.uniform(0, 200))))})
        cust = pd.DataFrame(rows)
        orows = [{"order_id": o.order_id, "customer_id": o.crm_id, "ordered_at": o.ts, "order_channel": o.channel, "status": o.status,
                  "order_total": o.total, "discount_amount": o.discount, "refund_amount": o.refund, "currency": "USD",
                  "external_ref": o.external_ref, "coupon_code": o.coupon, "items_count": o.items} for o in self.orders]
        return cust, pd.DataFrame(orows)

    def render_ads(self) -> pd.DataFrame:
        rng = self.rng
        sdf = pd.DataFrame({"cmp": [s.cmp.key for s in self.sessions], "day": [s.start.date() for s in self.sessions]})
        counts = sdf.groupby(["cmp", "day"]).size().to_dict()
        revenue = sum(o.net - o.refund for o in self.orders if o.in_window and o.channel != "store" and o.status == "completed")
        s_total = revenue / self.target_mer
        by_pid: dict[str, list[Sess]] = {}
        for s in self.sessions:
            by_pid.setdefault(s.pid, []).append(s)
        claims: dict[tuple, list] = {}
        for o in self.orders:
            if not (o.in_window and o.channel != "store" and o.status != "cancelled"):
                continue
            seen = set()
            for s in by_pid.get(o.person.pid, []):
                if s.cmp.is_paid and o.ts - timedelta(days=7) <= s.start <= o.ts and s.cmp.key not in seen:
                    seen.add(s.cmp.key)
                    a = claims.setdefault((s.cmp.key, o.ts.date()), [0, 0.0])
                    a[0] += 1
                    a[1] += o.net
        rows = []
        for ci, c in enumerate(PAID):
            n = np.array([counts.get((c.key, d), 0) for d in DAYS], float)
            clicks = np.round(n / 0.94 * np.exp(rng.normal(0, .03, N_DAYS)))
            mean = clicks[clicks > 0].mean() if (clicks > 0).any() else 1.0
            raw = np.where(clicks > 0, (clicks / mean) ** (1 + c.gamma) * np.exp(rng.normal(0, .06, N_DAYS)), 0.0)
            cost = s_total * c.budget_share * raw / max(raw.sum(), 1e-9)
            imps = np.round(clicks / c.ctr * np.exp(rng.normal(0, .05, N_DAYS)))
            for di, d in enumerate(DAYS):
                cl = claims.get((c.key, d), [0, 0.0])
                rows.append({"date": d, "platform": c.platform, "account_id": f"acct-{c.platform}", "campaign_id": f"{c.platform[:3]}-{1001 + ci}",
                             "campaign_name": f"{c.channel_group} | {c.campaign}", "utm_source": c.source, "utm_medium": c.medium,
                             "utm_campaign": c.campaign, "impressions": int(imps[di]), "clicks": int(clicks[di]),
                             "cost": round(float(cost[di]), 2), "currency": "USD",
                             "platform_conversions": round(cl[0] * c.overclaim, 2), "platform_conversion_value": round(cl[1] * c.overclaim, 2)})
        self.total_paid_spend = float(s_total)
        return pd.DataFrame(rows)

    def render_truth(self) -> dict:
        ts = pd.DataFrame([{"session_key": s.key, "device_id": s.device_id, "source_system": "ga4" if s.kind == "web" else "segment",
                            "true_person_id": s.pid, "channel_group": s.cmp.channel_group, "campaign_key": s.cmp.campaign_key,
                            "session_start_ts": s.start, "is_bounce": s.bounce} for s in self.sessions])
        to = pd.DataFrame([{"order_id": o.order_id, "true_person_id": o.person.pid, "crm_customer_id": o.crm_id, "ordered_at": o.ts,
                            "order_channel": o.channel, "is_first_order": o.is_first, "in_window": o.in_window,
                            "online_tracked": o.online_tracked} for o in self.orders])
        crm_map = pd.DataFrame([{"crm_customer_id": cid, "true_person_id": p.pid, "dup_kind": p.dup_kind}
                                for p in self.persons if p.is_crm for cid, *_ in p.crm_ids])
        shared = {}
        for p in self.persons:
            for b in p.browsers:
                shared.setdefault(b.ga_id, set()).add(p.pid)
        camps = pd.DataFrame([{"campaign_key": c.campaign_key, "campaign_id": c.key, "channel_group": c.channel_group, "truth_weight": c.truth_w,
                               "is_paid": c.is_paid, "gamma": c.gamma, "true_elasticity": c.beta if c.is_paid else np.nan,
                               "budget_share": c.budget_share} for c in CAMPAIGNS])
        params = pd.DataFrame([{"key": k, "value": float(v)} for k, v in BGNBD_TRUE.items()] +
                              [{"key": "shared_devices", "value": float(sum(len(v) > 1 for v in shared.values()))}])
        return {"truth_sessions": ts, "truth_orders": to, "truth_crm_map": crm_map, "truth_campaigns": camps, "truth_params": params}

    # ---- main
    def run(self) -> SimResult:
        rng = self.rng
        n_crm = int(self.n_persons * self.crm_rate)
        for i in range(self.n_persons):
            p = self.make_person(i, is_crm=i < n_crm)
            self.persons.append(p)
        crm_buyers = [p for p in self.persons if p.is_crm]
        for p in crm_buyers:
            self.plan_orders(p)
            self.assign_crm(p)
        # households that share one browser (two different people, one device)
        cand = [p for p in crm_buyers if p.is_buyer and p.consent and p.seg_web and p.browsers[0].valid_from is None and p.browsers[0].valid_to is None]
        idx = rng.permutation(len(cand))[: int(0.03 * len(cand)) * 2]
        for a, b in zip(idx[0::2], idx[1::2]):
            cand[b].browsers[0] = cand[a].browsers[0]
        for p in crm_buyers:
            self.materialize_orders(p)
            self.browse_sessions(p)
        for p in self.persons:
            if not p.is_crm:
                self.anon_sessions(p)
        self.bounce_sessions()
        self.finalize_sessions()
        ga4_path = self.write_ga4()
        ident, tracks, seg_orders = self.render_segment()
        cust, crm_orders = self.render_crm()
        ads = self.render_ads()
        truth = self.render_truth()
        online = [o for o in self.orders if o.in_window and o.channel != "store"]
        summary = {
            "persons": self.n_persons, "crm_customers": len(cust), "crm_orders": len(crm_orders),
            "orders_in_window": sum(o.in_window for o in self.orders), "online_orders_in_window": len(online),
            "online_orders_tracked": sum(o.online_tracked for o in online),
            "sessions_web": sum(s.kind == "web" for s in self.sessions), "sessions_app": sum(s.kind == "app" for s in self.sessions),
            "ga4_events": self.n_ga4_events, "segment_tracks": len(tracks), "segment_identifies": len(ident),
            "paid_spend": round(self.total_paid_spend, 2),
            "online_net_revenue": round(sum(o.net - o.refund for o in online if o.status == "completed"), 2),
        }
        tables = {"crm_customers": cust, "crm_orders": crm_orders, "segment_identifies": ident, "segment_tracks": tracks,
                  "segment_order_completed": seg_orders, "ads_spend_daily": ads}
        return SimResult(ga4_path, tables, truth, summary)


PRESETS = {
    "small": dict(n_persons=800, bounce_per_day=60),
    "medium": dict(n_persons=6000, bounce_per_day=450),
    "large": dict(n_persons=20000, bounce_per_day=1500),
}


def simulate(scale: str = "medium", seed: int = 42, **overrides) -> SimResult:
    kw = {**PRESETS[scale], **overrides}
    return Simulator(seed=seed, **kw).run()
