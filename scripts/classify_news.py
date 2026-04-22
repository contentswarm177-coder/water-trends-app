"""One-shot news classification pass (Pattern 1).

Applies relevance scoring + angle tagging + notability flagging to each
article in data/news_mentions.json, writing the enriched result to
data/news_scored.json. Designed to be run interactively from a Claude
Code session (uses the Max subscription, zero incremental cost).

Uses regex-based rules for the broad strokes, with explicit overrides
by article index for items the rules don't get right.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INPUT = REPO_ROOT / "data" / "news_mentions.json"
OUTPUT = REPO_ROOT / "data" / "news_scored.json"


# ------------------------------------------------------------------
# Rule-based classifier
# ------------------------------------------------------------------

NOISE_TERMS = [
    r"\bcoachella\b", r"\bgatorade\b", r"\bcelebrit", r"\bhollywood\b",
    r"\bsex advice\b", r"\brubberneck", r"\bfestival pizza\b",
    r"\bbernie sanders\b", r"\bronda rousey\b", r"\belon musk\b",
    r"\bshaq\b", r"\bperplexity\b", r"\bking charles\b",
    r"\bjazz fest\b", r"\brfk\b", r"\bkennedy\b",
    r"\bstock position\b", r"\bprice target\b", r"earnings (call|transcript)",
    r"\bcoca.?cola\b", r"\bpepsico\b", r"\bclorox\b",
    r"\ballocates?\b.*\bstock\b", r"\binvestment counsel\b",
    r"\bgrows? stake\b", r"\btrims? stock\b", r"\bacquires? new stake\b",
    r"\brating lowered\b", r"\brepor(t|ter) [a-z]+$",  # author pages
    r"\bauthor\b|\bcolumn\b",
    r"\bbattery\b.*\bpack\b", r"\bbackpack\b.*\bworth\b", r"\bbong\b",
    r"\bmattress\b", r"\bkickoff\b", r"\bbasketball\b",
    r"\bwrestling\b", r"\bufc\b", r"\bshaq\b",
    r"\bschonder\b", r"\bthompson\b$", r"\bgabrielle\b",
    r"\bguardrail\b", r"\btractor.trailer\b.*\breservoir\b",  # news briefs
    r"\bdata center\b(?!s? (cooling|water))",
    r"\biraqi captain\b", r"\bsailing\b",
    r"\bsuperbug\b", r"\bdiarrhea\b",
    r"\bstablecoin\b", r"\bcrypto\b",
    r"\bpsyched?elic", r"\bflea treatment",
    r"\bmahogany\b", r"\bflag of truce\b",
    r"\blargest homes\b", r"\bhomes for sale\b",
    r"\bpizza\b", r"\brestaurant\b",
    r"\bveterans news\b", r"\bcommunity calendar\b",
    r"\bweekly home sales\b", r"\bhomes for sale\b", r"\bhouse of the week\b",
    r"\bweekend roundup\b", r"\bwhat.?s up, nepa\b",
    r"\bfund stock\b", r"\bheads? up display\b",
    r"\bfinance\b.*\beducation\b",  # news.mit.edu about India
    r"\bshark habitat\b", r"\bgala\b",
    r"\bfreeland man\b", r"\bmurdering\b",
    r"\bwaterboy\b", r"\bnate diaz\b",
    r"\bsaboteur\b", r"\bbusinessmen accuse\b",
    r"\bindia economic\b", r"\bprimary\b",
    r"\bcrypto\b", r"\bprince\b",
    r"\bbrenda king\b",  # human interest
    r"\balgae\b(?! (bloom|in))",  # if "algae" but not about drinking water algae
    r"\b\$120k\b",
    r"\bbong\b", r"\bmaple\b(?! syrup)",  # decorative patterns
    r"\breckitt\b",  # earnings
    r"\bbrand failures\b",
    r"\bbusiness briefs\b",
    r"\bcalendar of events\b",
    r"\bdiverting\b.*\bgoal\b",
    r"\bcompetition\b$",
    r"\bticket info\b",
    r"\bpaper packaging\b",
    r"\bmorningstar\b",
    r"\bstock rating\b",
    r"\bgoodhouse?keeping\b",
    r"\bcookware review\b",
    r"\binterior.?exterior\b",
]

HIGH_SIGNAL_TERMS = [
    r"\btighten(s|ing) limits\b", r"\bnew (rules|limits)\b",
    r"\bepa (targets|delays|launches|proposes|adopts)\b",
    r"\bdrinking water\b",
    r"\bboil water\b", r"\bboil order\b", r"\bdo not drink\b",
    r"\bwater main break\b", r"\bwater advisory\b",
    r"\be\.\s*coli\b", r"\bcontamination\b",
    r"\blead service line\b", r"\blead contamination\b",
    r"\bwell water (testing|warning|advisory|safety)\b",
    r"\bpfas (detected|plan|rule|limit|cleanup|study|investigation)\b",
    r"\bforever chemicals?\b.*\b(drinking|investigat|rule|limit|detected|found)\b",
    r"\b(arsenic|nitrate|chromium|atrazine)\b.*\bwater\b",
    r"\bfluorid(e|ation)\b.*\b(water|city|limit|rule|vote|ban)\b",
    r"\bwater treatment\b", r"\bwater quality\b(?!.{0,30}\beducation\b)",
    r"\bsafe drinking\b",
    r"\bwater crisis\b", r"\bwater pickup\b",
    r"\bdrink(ing)? water (safe|project|plan|warning)\b",
]

CONSUMER_TERMS = [
    r"\bwater filter\b.{0,30}\b(expert|really need|best)\b",
    r"\bchange your.*\bfilter cartridge\b",
    r"\bwashing machine\b",
    r"\bdescale\b", r"\bhumidifier\b",
    r"\bmicroplastics? in\b.{0,20}\b(water|drinking)\b",
]

SCIENCE_TERMS = [
    r"\bpfas study\b", r"\bmicroplastics? study\b",
    r"\bpenguins? find\b", r"\bdolphin\b",
    r"\blab gloves\b", r"\bscience of\b",
]


def rule_classify(article: dict) -> tuple[int, str, bool, str]:
    title = (article.get("title") or "").lower()

    for pattern in NOISE_TERMS:
        if re.search(pattern, title, re.I):
            return (1, "noise", False, "keyword token appears but article off-topic")

    for pattern in HIGH_SIGNAL_TERMS:
        if re.search(pattern, title, re.I):
            angle = "regulatory" if re.search(
                r"\b(epa|rule|limit|tighten|adopt|regulat|classif|approv|vote|investigat)",
                title, re.I,
            ) else "crisis" if re.search(
                r"\b(boil|advisory|do not drink|contamination|crisis|warn|spill|coli)\b",
                title, re.I,
            ) else "water-quality"
            return (9, angle, True, "direct water-quality / regulatory / crisis coverage")

    for pattern in CONSUMER_TERMS:
        if re.search(pattern, title, re.I):
            return (7, "consumer", False, "Culligan product-category consumer content")

    for pattern in SCIENCE_TERMS:
        if re.search(pattern, title, re.I):
            return (6, "science", False, "water-quality research coverage")

    return (4, "tangential", False, "keyword appears, relevance unclear")


# ------------------------------------------------------------------
# Manual overrides — index (1-based) → (score, angle, notable, reason)
# Applied AFTER the rule pass so they win on tie.
# ------------------------------------------------------------------

OVERRIDES: dict[int, tuple[int, str, bool, str]] = {
    # Clear noise the rules might miss
    1: (1, "noise", False, "Georgia wildfire state of emergency, not water quality"),
    3: (3, "lifestyle", False, "Adopt-a-Beach awareness; tangential"),
    5: (1, "noise", False, "Navy divers recovering Orion space capsule"),
    7: (2, "noise", False, "wildfire community response, not water"),
    8: (1, "noise", False, "wildfire evacuation advice"),
    10: (2, "noise", False, "PR/brand launch, not news"),
    11: (2, "noise", False, "wildfire relief effort"),
    13: (1, "noise", False, "Reckitt earnings report"),
    14: (2, "noise", False, "wildfire donation drive"),
    15: (1, "noise", False, "football transfer commentary"),
    17: (1, "noise", False, "hollywood celebrity roundup"),
    19: (4, "lifestyle", False, "americans picky about water - lightweight consumer piece"),
    20: (2, "crisis", False, "typhoon recovery, not drinking water focused"),
    24: (1, "noise", False, "maple syrup farm expansion"),
    32: (2, "noise", False, "home renovation trends general"),
    33: (1, "noise", False, "fly fishing hotel booking"),
    34: (2, "lifestyle", False, "zoo conservation partnership"),
    44: (1, "noise", False, "podcast episode about nothing specific"),
    47: (8, "regulatory", True, "local govt PFAS funding request"),
    55: (1, "noise", False, "MIT piece on India economic development"),
    56: (9, "regulatory", True, "Lewiston water treatment funding"),
    58: (1, "noise", False, "Jane Fonda earth day musical"),
    60: (2, "consumer", False, "earth day shopping deals"),
    62: (2, "consumer", False, "earth day sales"),
    70: (1, "noise", False, "AZZ earnings call"),
    71: (1, "noise", False, "Helen of Troy earnings"),
    72: (4, "lifestyle", False, "americans picky water survey - duplicate-ish"),
    73: (5, "regulatory", False, "Trump rollback MAHA movement - mixed relevance"),
    74: (1, "noise", False, "Bernie Sanders rally"),
    82: (1, "noise", False, "power outage advisory"),
    83: (1, "noise", False, "targeted news service masthead"),
    84: (10, "regulatory", True, "Maine tightens PFAS limits — flagship regulatory story"),
    85: (7, "consumer", False, "bottled vs tap taste comparison"),
    86: (3, "crisis", False, "wildfire coverage"),
    87: (9, "science", True, "fluoride IQ study - comms-relevant narrative"),
    88: (5, "consumer", False, "Walmart bottled water rollout"),
    89: (1, "noise", False, "sustainable wardrobe patches"),
    90: (2, "crisis", False, "wildfire road closure"),
    91: (6, "science", False, "flushable wipes editorial"),
    92: (5, "lifestyle", False, "local waterworks profile"),
    93: (2, "lifestyle", False, "small town cleanup"),
    94: (1, "noise", False, "weekly events roundup"),
    95: (9, "crisis", True, "Kalamazoo jail water crisis"),
    96: (8, "crisis", True, "PFAS in clothing mainstream coverage"),
    97: (7, "science", False, "microplastics everywhere coverage"),
    98: (1, "noise", False, "bride vengeance story"),
    99: (3, "crisis", False, "reservoir crash insurance"),
    100: (10, "regulatory", True, "judge dissolves fluoride restoration order"),
    101: (1, "noise", False, "cheap bathroom gadgets"),
    103: (1, "noise", False, "fiesta travel tips"),
    110: (1, "noise", False, "techdirt author page"),
    111: (1, "noise", False, "protest arrests - not water"),
    112: (1, "noise", False, "techdirt story stub"),
    113: (1, "noise", False, "techdirt author page"),
    114: (2, "noise", False, "state rep election announcement"),
    115: (1, "noise", False, "flossing products"),
    116: (1, "noise", False, "nassau weekly student lit"),
    118: (1, "noise", False, "king charles trivia"),
    121: (1, "noise", False, "backpacker gear review"),
    123: (4, "lifestyle", False, "state earth week announcement"),
    124: (1, "noise", False, "amazon bestsellers"),
    125: (4, "consumer", False, "chlorophyll water walmart launch"),
    126: (3, "lifestyle", False, "public trust opinion piece"),
    132: (1, "noise", False, "top food brand failures"),
    133: (1, "noise", False, "cocacola stock"),
    134: (10, "regulatory", True, "nitrate polluting wells — major comms story"),
    135: (1, "noise", False, "cocacola stock"),
    136: (2, "lifestyle", False, "data centers - not water quality"),
    137: (1, "noise", False, "homes for sale la crosse"),
    138: (7, "lifestyle", False, "florida springs under threat"),
    139: (2, "lifestyle", False, "data centers midterms politics"),
    141: (1, "noise", False, "pepsico stock"),
    142: (1, "noise", False, "iraqi captain sailing war"),
    144: (1, "noise", False, "mission trip profile"),
    145: (3, "lifestyle", False, "cigarette butt cleanup"),
    146: (1, "noise", False, "coachella pizza"),
    149: (1, "noise", False, "student cleanup"),
    150: (3, "consumer", False, "smart home tech roundup"),
    152: (1, "noise", False, "radio station masthead"),
    153: (1, "noise", False, "jazz fest ticket info"),
    154: (4, "science", False, "engineering speaker series"),
    156: (1, "noise", False, "author page"),
    157: (1, "noise", False, "cocacola stock"),
    158: (1, "noise", False, "cocacola stock"),
    160: (3, "lifestyle", False, "aquarium water tip"),
    161: (2, "lifestyle", False, "UK pet flea treatments"),
    162: (1, "noise", False, "veterans news weekly"),
    163: (4, "consumer", False, "washing machine cleaning"),
    164: (1, "noise", False, "coca cola femsa stock"),
    165: (2, "lifestyle", False, "citywide cleanup"),
    167: (1, "noise", False, "embotelladora stock comparison"),
    169: (1, "noise", False, "superbug NY spread"),
    170: (3, "consumer", False, "shower cartridge repair"),
    171: (1, "noise", False, "psychedelics executive order"),
    172: (4, "consumer", False, "washing machine cleaning"),
    174: (2, "lifestyle", False, "west seattle duwamish event"),
    175: (1, "noise", False, "hexclad cookware review"),
    181: (1, "noise", False, "barter items prepper list"),
    183: (8, "regulatory", True, "city water treatment funding"),
    186: (1, "noise", False, "weekly events"),
    188: (1, "noise", False, "GE filter product listing SEO"),
    192: (1, "noise", False, "embotelladora stock comparison"),
    193: (3, "crisis", False, "reservoir fatality truck crash"),
    195: (1, "noise", False, "ronda rousey UFC"),
    196: (1, "noise", False, "murder case"),
    197: (3, "crisis", False, "chicago flood warning"),
    199: (1, "noise", False, "hiking trails for beginners"),
    200: (1, "noise", False, "perplexity AI CEO"),
    202: (1, "noise", False, "UH student award"),
    206: (1, "noise", False, "pearl without spending big"),
    207: (5, "science", False, "microplastics blood pressure research"),
    208: (1, "noise", False, "oil majors strait of hormuz"),
    209: (7, "crisis", False, "blue green algae lake advisory"),
    213: (1, "noise", False, "album review"),
    220: (1, "noise", False, "canada business growth delta"),
    221: (1, "noise", False, "condo sales"),
    222: (1, "noise", False, "house of the week"),
    223: (1, "noise", False, "border wall land seizure"),
    224: (2, "science", False, "lab research SLAM event"),
    225: (5, "science", False, "dioxins in food chain"),
    226: (3, "lifestyle", False, "earth day opinion"),
    227: (1, "noise", False, "gatorade rebrand"),
    229: (1, "noise", False, "business briefs"),
    230: (1, "noise", False, "veterans resource fair"),
    232: (1, "noise", False, "homes for sale"),
    234: (4, "lifestyle", False, "CEO Q&A"),
    237: (2, "science", False, "colorectal cancer article"),
    238: (1, "noise", False, "stablecoin policy"),
    239: (1, "noise", False, "bong beginner guide"),
    240: (3, "lifestyle", False, "plant-based packaging trend"),
    241: (1, "noise", False, "shaq lifestyle"),
    243: (4, "lifestyle", False, "historic status water facility"),
    244: (1, "noise", False, "flight skincare"),
    247: (3, "regulatory", False, "firefighter equipment funding"),
    248: (1, "noise", False, "mattress opinion"),
    249: (1, "noise", False, "UAE infrastructure"),
    250: (1, "noise", False, "gatorade rebrand"),
    251: (3, "consumer", False, "humidifier descaling guide"),
    253: (1, "noise", False, "pond fund easement"),
    255: (1, "noise", False, "austin earth day events"),
    257: (1, "noise", False, "FDA peptides"),
    259: (1, "noise", False, "RFK Jr hearings"),
    262: (1, "noise", False, "gatorade pepsi pivot"),
    264: (1, "noise", False, "RFK Jr snap"),
    266: (5, "regulatory", False, "senate bill flood risk disclosure"),
    267: (1, "noise", False, "calendar of events"),
    268: (1, "noise", False, "sci-fi upgrade film"),
    270: (1, "noise", False, "RFK Jr panic"),
    272: (1, "noise", False, "gatorade rebrand"),
    273: (2, "lifestyle", False, "EPCAMR cleanup volunteers"),
    274: (1, "noise", False, "weekend roundup"),
    277: (1, "noise", False, "business briefs"),
    278: (1, "noise", False, "elon musk lifestyle"),
    279: (2, "lifestyle", False, "earth day festival"),
    280: (1, "noise", False, "environmental field education anniversary"),
    282: (1, "noise", False, "epetwater purchase order"),
    283: (1, "noise", False, "noise pollution animals"),
    284: (6, "science", False, "zero liquid discharge review"),
    286: (3, "lifestyle", False, "seabed debris cleanup"),
    288: (1, "noise", False, "local events"),
    291: (4, "science", False, "chemical exposure panel"),
    293: (1, "noise", False, "shark habitat research"),
    294: (2, "consumer", False, "tankless water heater repair"),
    295: (1, "noise", False, "STEM win athletics"),
    296: (1, "noise", False, "pepto-bismol traveler diarrhea"),
    297: (1, "noise", False, "oak mountain high school"),
    300: (1, "noise", False, "car finance relationship advice"),
    301: (1, "noise", False, "retro arcade amazon"),
    302: (3, "lifestyle", False, "sustainable travel providers"),
    305: (1, "noise", False, "trevor lee businessmen accusation"),
}


def classify_article(index: int, article: dict) -> dict:
    # Overrides first
    if index in OVERRIDES:
        score, angle, notable, reason = OVERRIDES[index]
    else:
        score, angle, notable, reason = rule_classify(article)
    return {
        "relevance_score": score,
        "primary_angle": angle,
        "notable": notable,
        "classification_reason": reason,
    }


def main() -> int:
    data = json.loads(INPUT.read_text())
    mentions = data["mentions"]

    angle_counts: dict[str, int] = {}
    score_buckets = {"high (8-10)": 0, "medium (5-7)": 0, "low (2-4)": 0, "noise (0-1)": 0}

    for idx, article in enumerate(mentions, 1):
        cls = classify_article(idx, article)
        article.update(cls)
        angle_counts[cls["primary_angle"]] = angle_counts.get(cls["primary_angle"], 0) + 1
        s = cls["relevance_score"]
        if s >= 8:
            score_buckets["high (8-10)"] += 1
        elif s >= 5:
            score_buckets["medium (5-7)"] += 1
        elif s >= 2:
            score_buckets["low (2-4)"] += 1
        else:
            score_buckets["noise (0-1)"] += 1

    data["classified_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data["classifier"] = "pattern-1 manual (rules + overrides)"
    data["mentions"] = sorted(mentions, key=lambda m: m.get("relevance_score", 0), reverse=True)

    OUTPUT.write_text(json.dumps(data, indent=2))

    print(f"Classified {len(mentions)} articles:")
    print(f"  by score: {score_buckets}")
    print(f"  by angle: {angle_counts}")
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
