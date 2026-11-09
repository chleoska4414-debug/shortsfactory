"""Data-driven knowledge-card content packs.

Each topic is a list of "cards". A card is a dict with:
    - headline: a short punchy title for the card
    - fact: the informational body spoken/shown for that card

New topics are added purely as data here; no code changes are required. Providers in the
script/ package turn these packs into a narration script.
"""

from __future__ import annotations

from typing import Dict, List

Card = Dict[str, str]

TOPICS: Dict[str, List[Card]] = {
    "space": [
        {
            "headline": "A Day on Venus",
            "fact": "A single day on Venus is longer than its entire year, because it spins incredibly slowly.",
        },
        {
            "headline": "Silent Space",
            "fact": "Space is almost completely silent because there is no air to carry sound waves.",
        },
        {
            "headline": "Neutron Star Density",
            "fact": "A teaspoon of neutron star material would weigh about a billion tons on Earth.",
        },
        {
            "headline": "The Sun's Mass",
            "fact": "The Sun accounts for about 99.8 percent of all the mass in our solar system.",
        },
        {
            "headline": "Footprints Forever",
            "fact": "The footprints left on the Moon could last for millions of years with no wind to erase them.",
        },
        {
            "headline": "Floating Water",
            "fact": "Astronomers found a water cloud in space holding 140 trillion times the water of Earth's oceans.",
        },
    ],
    "history": [
        {
            "headline": "Oxford Beats the Aztecs",
            "fact": "Oxford University is older than the Aztec Empire, with teaching dating back to 1096.",
        },
        {
            "headline": "Cleopatra's Timeline",
            "fact": "Cleopatra lived closer in time to the Moon landing than to the building of the Great Pyramid.",
        },
        {
            "headline": "The Shortest War",
            "fact": "The shortest war in history lasted around 38 minutes between Britain and Zanzibar in 1896.",
        },
        {
            "headline": "Ancient Chewing Gum",
            "fact": "People chewed a form of gum made from birch bark tar over 5,000 years ago.",
        },
        {
            "headline": "Napoleon's Rabbits",
            "fact": "Napoleon was once swarmed and chased by a horde of tame rabbits during a hunt.",
        },
        {
            "headline": "Tea Before England",
            "fact": "Tea was popular in China for thousands of years before it ever reached Europe.",
        },
    ],
    "psychology": [
        {
            "headline": "The Mere Exposure Effect",
            "fact": "People tend to like things more simply because they have seen them before.",
        },
        {
            "headline": "The Spotlight Illusion",
            "fact": "We overestimate how much others notice our mistakes; most people barely register them.",
        },
        {
            "headline": "Dunbar's Number",
            "fact": "The human brain can comfortably maintain only about 150 stable social relationships.",
        },
        {
            "headline": "The Zeigarnik Effect",
            "fact": "Unfinished tasks stick in our memory far more stubbornly than completed ones.",
        },
        {
            "headline": "Color and Appetite",
            "fact": "The color blue can suppress appetite, which is why it is rare in food packaging.",
        },
        {
            "headline": "Smiling Changes Mood",
            "fact": "Simply forcing a smile can nudge your brain toward feeling genuinely happier.",
        },
    ],
    "health": [
        {
            "headline": "Your Fasting Heart",
            "fact": "The human heart beats about 100,000 times every single day without a break.",
        },
        {
            "headline": "Laughter Burns Calories",
            "fact": "Ten to fifteen minutes of real laughter can burn up to 40 calories.",
        },
        {
            "headline": "Bones vs Steel",
            "fact": "Ounce for ounce, human bone is stronger than steel in resisting compression.",
        },
        {
            "headline": "The Sleepy Brain Clean",
            "fact": "During deep sleep your brain flushes out waste proteins linked to memory decline.",
        },
        {
            "headline": "Stomach Acid Power",
            "fact": "Your stomach acid is strong enough to dissolve metal, yet it renews its lining constantly.",
        },
        {
            "headline": "Walking Boosts Ideas",
            "fact": "Studies show that walking can increase creative output by up to 60 percent.",
        },
    ],
}


def list_topics() -> List[str]:
    """Return the sorted names of all available topic packs."""
    return sorted(TOPICS.keys())


def get_topic(name: str) -> List[Card]:
    """Return the card list for a topic pack.

    Raises:
        KeyError: if the topic name is not known. The message lists valid topics.
    """
    key = (name or "").strip().lower()
    if key not in TOPICS:
        available = ", ".join(list_topics())
        raise KeyError(f"Unknown topic '{name}'. Available topics: {available}")
    return TOPICS[key]
