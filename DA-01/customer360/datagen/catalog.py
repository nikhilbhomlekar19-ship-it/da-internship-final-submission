"""Marketing campaign catalogue used by the simulator.

The numbers here are *simulation assumptions*, chosen so that the typical attribution biases show up:
  * brand search / retargeting / coupon affiliates / direct close sales that other channels started (last-touch heroes)
  * prospecting social, generic search, TikTok and content affiliates introduce customers (first-touch heroes)
`truth_w` is the (hidden) true incrementality of a touch. It is only used to build the ground-truth credit that the
evaluation step compares each attribution model against.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Campaign:
    key: str
    channel_group: str
    source: str
    medium: str
    campaign: str
    platform: str | None = None  # ad platform name -> campaign has spend; None = unpaid
    disc: float = 0.0   # propensity to appear as FIRST touch of a converting journey
    mid: float = 0.0    # ... as a MIDDLE touch
    close: float = 0.0  # ... as the LAST (converting) touch
    vol: float = 0.0    # share of non-converting traffic (anonymous browsers / bounces)
    truth_w: float = 0.5
    budget_share: float = 0.0  # share of total paid budget
    gamma: float = 0.0  # cost-curve exponent: cost ~ clicks^(1+gamma)  => revenue ~ spend^(1/(1+gamma))
    ctr: float = 0.01
    crm_only: bool = False  # reachable only for people already in the CRM (email / push)
    app_only: bool = False
    overclaim: float = 1.0  # how much the ad platform over-reports conversions (view-through, modelled)

    @property
    def campaign_key(self) -> str:
        return f"{self.source}|{self.medium}|{self.campaign}".lower()

    @property
    def is_paid(self) -> bool:
        return self.platform is not None

    @property
    def beta(self) -> float:
        """True spend->revenue elasticity implied by the cost curve."""
        return 1.0 / (1.0 + self.gamma) if self.is_paid else float("nan")


C = Campaign
CAMPAIGNS: list[Campaign] = [
    # ---- Paid search
    C("ps_brand", "Paid Search", "google", "cpc", "brand_core", "google_ads", .02, .08, .20, .04, .25, .12, .55, .12, overclaim=1.15),
    C("ps_generic", "Paid Search", "google", "cpc", "generic_apparel", "google_ads", .12, .10, .06, .07, 1.0, .10, .30, .05, overclaim=1.15),
    C("ps_shopping", "Paid Search", "google", "cpc", "pmax_shopping", "google_ads", .09, .09, .07, .06, .80, .12, .35, .05, overclaim=1.25),
    C("ps_bing", "Paid Search", "bing", "cpc", "brand_core", "bing_ads", .01, .03, .05, .01, .25, .02, .50, .09, overclaim=1.10),
    # ---- Paid social
    C("psoc_prospect", "Paid Social", "facebook", "paid_social", "lal_prospecting", "meta_ads", .17, .09, .01, .12, .90, .20, .30, .012, overclaim=1.45),
    C("psoc_retarget", "Paid Social", "facebook", "paid_social", "dpa_retargeting", "meta_ads", .00, .06, .10, .03, .45, .08, .50, .020, overclaim=1.60),
    C("psoc_tiktok", "Paid Social", "tiktok", "paid_social", "spark_ugc", "tiktok_ads", .10, .05, .01, .09, .80, .06, .25, .010, overclaim=1.50),
    # ---- Display
    C("disp_prospect", "Display", "dv360", "display", "prospecting_banner", "dv360", .09, .04, .00, .13, .55, .12, .25, .004, overclaim=1.70),
    C("disp_rmkt", "Display", "google", "display", "rmkt_banner", "google_ads", .00, .05, .06, .03, .25, .06, .45, .006, overclaim=1.60),
    # ---- Affiliate
    C("aff_coupon", "Affiliate", "cj", "affiliate", "coupon_sites", "cj_affiliate", .01, .03, .09, .03, .20, .07, .60, .030, overclaim=1.10),
    C("aff_content", "Affiliate", "impact", "affiliate", "content_partners", "impact_affiliate", .05, .03, .02, .03, .80, .05, .30, .020, overclaim=1.10),
    # ---- Owned / earned (no ad spend)
    C("email_promo", "Email", "klaviyo", "email", "promo_blast", None, .00, .10, .08, .00, .70, crm_only=True),
    C("email_flow", "Email", "klaviyo", "email", "abandoned_cart_flow", None, .00, .06, .10, .00, .80, crm_only=True),
    C("org_search", "Organic Search", "google", "organic", "(organic)", None, .16, .12, .07, .16, .60),
    C("org_social", "Organic Social", "instagram", "social", "(not set)", None, .05, .03, .01, .05, .40),
    C("referral", "Referral", "blog.fashionista.example", "referral", "(referral)", None, .04, .02, .01, .04, .50),
    C("direct", "Direct", "(direct)", "(none)", "(direct)", None, .03, .07, .14, .10, .15),
    C("app_push", "App Push", "braze", "push", "winback_push", None, .00, .03, .04, .00, .60, crm_only=True, app_only=True),
]
BY_KEY = {c.key: c for c in CAMPAIGNS}
PAID = [c for c in CAMPAIGNS if c.is_paid]

CHANNEL_ORDER = [
    "Paid Search", "Paid Social", "Display", "Affiliate", "Email", "App Push",
    "Organic Search", "Organic Social", "Referral", "Direct", "Other", "Unattributed",
]


def classify_channel(source: str | None, medium: str | None) -> str:
    """Python twin of the dbt macro c360_channel_group (used when building ad spend around the real GA4 sample)."""
    s, m = (source or "").lower(), (medium or "").lower()
    if s == "(direct)" and m in ("", "(none)", "(not set)"):
        return "Direct"
    if m in ("paid_social", "paidsocial", "social_paid", "cpc") and s in ("facebook", "instagram", "tiktok", "linkedin", "twitter", "pinterest", "snapchat", "meta"):
        return "Paid Social"
    if m in ("cpc", "ppc", "paidsearch", "paid_search"):
        return "Paid Search"
    if m in ("display", "cpm", "banner", "programmatic"):
        return "Display"
    if m == "affiliate":
        return "Affiliate"
    if m in ("email", "e-mail", "newsletter"):
        return "Email"
    if m in ("push", "app_push", "notification"):
        return "App Push"
    if m == "organic":
        return "Organic Search"
    if m in ("social", "social_organic", "social-network", "social-media"):
        return "Organic Social"
    if m == "referral":
        return "Referral"
    return "Other"
