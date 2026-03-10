#!/usr/bin/env python3
"""
03-extract.py — Genereer HTML + Tailwind componenten vanuit components-raw.json
"""
import json
import os
import re
import sys
from pathlib import Path

COMPONENTS_RAW = Path(__file__).resolve().parent / "components-raw.json"
OUT_DIR = Path(__file__).resolve().parent.parent / "components"
INDEX_PATH = Path(__file__).resolve().parent.parent / "index.json"
REPO_ROOT = Path(__file__).resolve().parent.parent


def slugify(name: str) -> str:
    name = name.lower()
    name = re.sub(r"[✨🆕]+", "", name)
    name = re.sub(r"[^a-z0-9\s\-]", "", name)
    name = name.strip()
    name = re.sub(r"[\s\-]+", "-", name)
    return name


def page_to_category(page_name: str) -> str:
    cleaned = re.sub(r"^\s*↳\s*", "", page_name).strip()
    return slugify(cleaned)


def describe_component(name: str, category: str) -> str:
    """Geef een korte beschrijving op basis van naam + categorie."""
    n = name.lower()
    if "split" in n:
        return f"{category.replace('-', ' ').title()} with split layout"
    if "centered" in n or "centre" in n:
        return f"Centered {category.replace('-', ' ')} layout"
    if "image" in n or "img" in n:
        return f"{category.replace('-', ' ').title()} with image"
    if "video" in n:
        return f"{category.replace('-', ' ').title()} with video"
    if "grid" in n:
        return f"{category.replace('-', ' ').title()} in grid layout"
    if "minimal" in n:
        return f"Minimal {category.replace('-', ' ')} variant"
    return f"{category.replace('-', ' ').title()} component: {name}"


def tags_for(name: str, category: str) -> list:
    tags = [category]
    name_lower = name.lower()
    for kw in ["split", "centered", "grid", "image", "video", "minimal", "dark", "light",
               "form", "modal", "sidebar", "table", "card", "banner", "hero", "cta",
               "navbar", "footer", "blog", "pricing", "team", "faq", "gallery",
               "stats", "timeline", "contact", "features", "logo"]:
        if kw in name_lower:
            tags.append(kw)
    return list(dict.fromkeys(tags))  # dedup


# --- HTML template builders per category ---

HTML_HEAD = """<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-white font-sans antialiased">
<!-- Relume: {name} | Category: {category} | ID: {node_id} -->
"""

HTML_FOOT = """
</body>
</html>
"""


def make_placeholder_image(classes="w-full h-64 bg-gray-200 rounded-lg flex items-center justify-center"):
    return f'<div class="{classes}"><span class="text-gray-400 text-sm">Image placeholder</span></div>'


def make_button(label="Get started", variant="primary"):
    if variant == "primary":
        return f'<a href="#" class="inline-flex items-center justify-center px-6 py-3 bg-black text-white text-sm font-semibold rounded-md hover:bg-gray-800 transition-colors">{label}</a>'
    return f'<a href="#" class="inline-flex items-center justify-center px-6 py-3 border border-gray-300 text-sm font-semibold rounded-md hover:bg-gray-50 transition-colors">{label}</a>'


LOREM = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Suspendisse varius enim in eros elementum tristique. Duis cursus, mi quis viverra ornare, eros dolor interdum nulla."
LOREM_SHORT = "Lorem ipsum dolor sit amet, consectetur adipiscing elit."

BUILDERS: dict = {}


def register(cats):
    def decorator(fn):
        for c in cats:
            BUILDERS[c] = fn
        return fn
    return decorator


@register(["navbars", "navbar"])
def build_navbar(name, category, node_id):
    is_centered = "centered" in name.lower()
    is_dark = "dark" in name.lower()
    bg = "bg-black" if is_dark else "bg-white"
    text = "text-white" if is_dark else "text-gray-900"
    border = "" if is_dark else "border-b border-gray-200"
    logo_text = "text-white" if is_dark else "text-black"
    links_color = "text-gray-300 hover:text-white" if is_dark else "text-gray-600 hover:text-gray-900"

    center_class = "justify-center" if is_centered else "justify-between"
    return f"""
<nav class="{bg} {border} sticky top-0 z-50 w-full">
  <div class="container mx-auto px-6 py-4 flex items-center {center_class} gap-8">
    <a href="#" class="font-bold text-xl {logo_text}">Brand</a>
    {"" if is_centered else ""}
    <ul class="hidden md:flex items-center gap-6">
      <li><a href="#" class="text-sm {links_color} transition-colors">Home</a></li>
      <li><a href="#" class="text-sm {links_color} transition-colors">About</a></li>
      <li><a href="#" class="text-sm {links_color} transition-colors">Services</a></li>
      <li><a href="#" class="text-sm {links_color} transition-colors">Blog</a></li>
      <li><a href="#" class="text-sm {links_color} transition-colors">Contact</a></li>
    </ul>
    <div class="flex items-center gap-3">
      {make_button("Log in", "secondary")}
      {make_button("Sign up")}
    </div>
    <button class="md:hidden p-2">
      <svg class="w-6 h-6 {logo_text}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
      </svg>
    </button>
  </div>
</nav>
"""


@register(["footers", "footer"])
def build_footer(name, category, node_id):
    is_dark = "dark" in name.lower()
    bg = "bg-black" if is_dark else "bg-gray-50"
    text = "text-gray-400" if is_dark else "text-gray-600"
    heading = "text-white" if is_dark else "text-gray-900"
    return f"""
<footer class="{bg} border-t border-gray-200 py-16">
  <div class="container mx-auto px-6">
    <div class="grid grid-cols-2 md:grid-cols-4 gap-8 mb-12">
      <div>
        <h3 class="font-bold text-sm {heading} mb-4">Company</h3>
        <ul class="space-y-2">
          <li><a href="#" class="text-sm {text} hover:text-gray-900">About</a></li>
          <li><a href="#" class="text-sm {text} hover:text-gray-900">Careers</a></li>
          <li><a href="#" class="text-sm {text} hover:text-gray-900">Press</a></li>
        </ul>
      </div>
      <div>
        <h3 class="font-bold text-sm {heading} mb-4">Product</h3>
        <ul class="space-y-2">
          <li><a href="#" class="text-sm {text} hover:text-gray-900">Features</a></li>
          <li><a href="#" class="text-sm {text} hover:text-gray-900">Pricing</a></li>
          <li><a href="#" class="text-sm {text} hover:text-gray-900">Security</a></li>
        </ul>
      </div>
      <div>
        <h3 class="font-bold text-sm {heading} mb-4">Resources</h3>
        <ul class="space-y-2">
          <li><a href="#" class="text-sm {text} hover:text-gray-900">Blog</a></li>
          <li><a href="#" class="text-sm {text} hover:text-gray-900">Documentation</a></li>
          <li><a href="#" class="text-sm {text} hover:text-gray-900">Support</a></li>
        </ul>
      </div>
      <div>
        <h3 class="font-bold text-sm {heading} mb-4">Legal</h3>
        <ul class="space-y-2">
          <li><a href="#" class="text-sm {text} hover:text-gray-900">Privacy</a></li>
          <li><a href="#" class="text-sm {text} hover:text-gray-900">Terms</a></li>
          <li><a href="#" class="text-sm {text} hover:text-gray-900">Cookies</a></li>
        </ul>
      </div>
    </div>
    <div class="border-t border-gray-200 pt-8 flex flex-col md:flex-row items-center justify-between gap-4">
      <p class="text-sm {text}">© 2025 Brand. All rights reserved.</p>
      <div class="flex items-center gap-4">
        <a href="#" class="text-sm {text} hover:text-gray-900">Twitter</a>
        <a href="#" class="text-sm {text} hover:text-gray-900">LinkedIn</a>
        <a href="#" class="text-sm {text} hover:text-gray-900">GitHub</a>
      </div>
    </div>
  </div>
</footer>
"""


@register(["hero-headers", "headers", "hero-headers-new", "cta-new"])
def build_hero(name, category, node_id):
    is_split = "split" in name.lower()
    is_centered = "centered" in name.lower() or ("split" not in name.lower() and "video" not in name.lower())
    is_dark = "dark" in name.lower()
    has_video = "video" in name.lower()
    bg = "bg-black" if is_dark else "bg-white"
    text = "text-white" if is_dark else "text-gray-900"
    sub = "text-gray-400" if is_dark else "text-gray-600"

    if is_split:
        return f"""
<section class="{bg} py-20 md:py-28">
  <div class="container mx-auto px-6 grid md:grid-cols-2 gap-12 items-center">
    <div>
      <p class="text-sm font-semibold {sub} uppercase tracking-wider mb-4">Tagline</p>
      <h1 class="text-4xl md:text-5xl font-bold {text} mb-6 leading-tight">Medium length hero heading goes here</h1>
      <p class="text-lg {sub} mb-8">{LOREM_SHORT}</p>
      <div class="flex items-center gap-4 flex-wrap">
        {make_button("Get started")}
        {make_button("Learn more", "secondary")}
      </div>
    </div>
    <div>
      {make_placeholder_image("w-full h-80 bg-gray-200 rounded-xl flex items-center justify-center")}
    </div>
  </div>
</section>
"""
    elif has_video:
        return f"""
<section class="{bg} py-20 md:py-32">
  <div class="container mx-auto px-6 text-center max-w-4xl">
    <p class="text-sm font-semibold {sub} uppercase tracking-wider mb-4">Tagline</p>
    <h1 class="text-4xl md:text-6xl font-bold {text} mb-6">Medium length hero heading goes here</h1>
    <p class="text-lg {sub} mb-8 max-w-2xl mx-auto">{LOREM_SHORT}</p>
    <div class="flex items-center justify-center gap-4 mb-12 flex-wrap">
      {make_button("Get started")}
      {make_button("Learn more", "secondary")}
    </div>
    <div class="w-full aspect-video bg-gray-200 rounded-xl flex items-center justify-center">
      <div class="w-16 h-16 bg-white rounded-full flex items-center justify-center shadow-lg">
        <svg class="w-6 h-6 text-gray-900 ml-1" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
      </div>
    </div>
  </div>
</section>
"""
    else:
        return f"""
<section class="{bg} py-20 md:py-32">
  <div class="container mx-auto px-6 text-center max-w-3xl">
    <p class="text-sm font-semibold {sub} uppercase tracking-wider mb-4">Tagline</p>
    <h1 class="text-4xl md:text-6xl font-bold {text} mb-6">Medium length hero heading goes here</h1>
    <p class="text-lg {sub} mb-8 max-w-xl mx-auto">{LOREM_SHORT}</p>
    <div class="flex items-center justify-center gap-4 flex-wrap">
      {make_button("Get started")}
      {make_button("Learn more", "secondary")}
    </div>
  </div>
</section>
"""


@register(["features"])
def build_features(name, category, node_id):
    is_centered = "centered" in name.lower()
    cols = "grid-cols-1 md:grid-cols-3" if "3" in name else "grid-cols-1 md:grid-cols-2"
    align = "text-center" if is_centered else "text-left"
    return f"""
<section class="bg-white py-16 md:py-24">
  <div class="container mx-auto px-6">
    <div class="{align} max-w-2xl {"mx-auto" if is_centered else ""} mb-12">
      <p class="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Tagline</p>
      <h2 class="text-3xl md:text-4xl font-bold text-gray-900 mb-4">Short heading here</h2>
      <p class="text-lg text-gray-600">{LOREM_SHORT}</p>
    </div>
    <div class="grid {cols} gap-8">
      {"".join([f'''
      <div class="{align}">
        <div class="w-12 h-12 bg-gray-100 rounded-lg flex items-center justify-center mb-4 {"mx-auto" if is_centered else ""}">
          <svg class="w-6 h-6 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/>
          </svg>
        </div>
        <h3 class="text-lg font-bold text-gray-900 mb-2">Feature {i+1}</h3>
        <p class="text-gray-600 text-sm">{LOREM_SHORT}</p>
      </div>''' for i in range(3)])}
    </div>
  </div>
</section>
"""


@register(["pricing", "pricing-pages"])
def build_pricing(name, category, node_id):
    return f"""
<section class="bg-white py-16 md:py-24">
  <div class="container mx-auto px-6">
    <div class="text-center max-w-2xl mx-auto mb-12">
      <p class="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Pricing</p>
      <h2 class="text-3xl md:text-4xl font-bold text-gray-900 mb-4">Simple, transparent pricing</h2>
      <p class="text-lg text-gray-600">{LOREM_SHORT}</p>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-5xl mx-auto">
      <div class="border border-gray-200 rounded-xl p-8">
        <h3 class="font-bold text-gray-900 mb-1">Starter</h3>
        <p class="text-gray-500 text-sm mb-6">For individuals</p>
        <p class="text-4xl font-bold text-gray-900 mb-6">€9<span class="text-lg font-normal text-gray-500">/mo</span></p>
        {make_button("Get started")}
        <ul class="mt-6 space-y-3">
          <li class="text-sm text-gray-600 flex items-center gap-2"><span class="text-green-500">✓</span> 5 projects</li>
          <li class="text-sm text-gray-600 flex items-center gap-2"><span class="text-green-500">✓</span> Basic analytics</li>
          <li class="text-sm text-gray-600 flex items-center gap-2"><span class="text-green-500">✓</span> Email support</li>
        </ul>
      </div>
      <div class="border-2 border-black rounded-xl p-8 relative">
        <span class="absolute -top-3 left-1/2 -translate-x-1/2 bg-black text-white text-xs px-3 py-1 rounded-full">Popular</span>
        <h3 class="font-bold text-gray-900 mb-1">Pro</h3>
        <p class="text-gray-500 text-sm mb-6">For teams</p>
        <p class="text-4xl font-bold text-gray-900 mb-6">€29<span class="text-lg font-normal text-gray-500">/mo</span></p>
        {make_button("Get started")}
        <ul class="mt-6 space-y-3">
          <li class="text-sm text-gray-600 flex items-center gap-2"><span class="text-green-500">✓</span> Unlimited projects</li>
          <li class="text-sm text-gray-600 flex items-center gap-2"><span class="text-green-500">✓</span> Advanced analytics</li>
          <li class="text-sm text-gray-600 flex items-center gap-2"><span class="text-green-500">✓</span> Priority support</li>
        </ul>
      </div>
      <div class="border border-gray-200 rounded-xl p-8">
        <h3 class="font-bold text-gray-900 mb-1">Enterprise</h3>
        <p class="text-gray-500 text-sm mb-6">For large orgs</p>
        <p class="text-4xl font-bold text-gray-900 mb-6">€99<span class="text-lg font-normal text-gray-500">/mo</span></p>
        {make_button("Get started")}
        <ul class="mt-6 space-y-3">
          <li class="text-sm text-gray-600 flex items-center gap-2"><span class="text-green-500">✓</span> Custom limits</li>
          <li class="text-sm text-gray-600 flex items-center gap-2"><span class="text-green-500">✓</span> SSO & SAML</li>
          <li class="text-sm text-gray-600 flex items-center gap-2"><span class="text-green-500">✓</span> Dedicated support</li>
        </ul>
      </div>
    </div>
  </div>
</section>
"""


@register(["faq"])
def build_faq(name, category, node_id):
    return f"""
<section class="bg-white py-16 md:py-24">
  <div class="container mx-auto px-6 max-w-3xl">
    <div class="text-center mb-12">
      <p class="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">FAQ</p>
      <h2 class="text-3xl md:text-4xl font-bold text-gray-900 mb-4">Frequently asked questions</h2>
    </div>
    <div class="space-y-4">
      {"".join([f'''
      <details class="border border-gray-200 rounded-lg">
        <summary class="px-6 py-4 font-semibold text-gray-900 cursor-pointer flex items-center justify-between">
          Question {i+1}: Lorem ipsum dolor sit amet?
          <span class="text-gray-400">+</span>
        </summary>
        <div class="px-6 pb-4 text-gray-600 text-sm leading-relaxed">{LOREM}</div>
      </details>''' for i in range(5)])}
    </div>
  </div>
</section>
"""


@register(["team"])
def build_team(name, category, node_id):
    return f"""
<section class="bg-white py-16 md:py-24">
  <div class="container mx-auto px-6">
    <div class="text-center max-w-2xl mx-auto mb-12">
      <p class="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Our Team</p>
      <h2 class="text-3xl md:text-4xl font-bold text-gray-900 mb-4">Meet our team</h2>
      <p class="text-lg text-gray-600">{LOREM_SHORT}</p>
    </div>
    <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-8">
      {"".join([f'''
      <div class="text-center">
        <div class="w-24 h-24 bg-gray-200 rounded-full mx-auto mb-4 flex items-center justify-center">
          <span class="text-gray-400 text-2xl">👤</span>
        </div>
        <h3 class="font-bold text-gray-900">Name Surname</h3>
        <p class="text-sm text-gray-500">Job title</p>
      </div>''' for i in range(4)])}
    </div>
  </div>
</section>
"""


@register(["contact", "contact-pages"])
def build_contact(name, category, node_id):
    is_split = "split" in name.lower()
    if is_split:
        return f"""
<section class="bg-white py-16 md:py-24">
  <div class="container mx-auto px-6 grid md:grid-cols-2 gap-12">
    <div>
      <p class="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Contact</p>
      <h2 class="text-3xl font-bold text-gray-900 mb-4">Get in touch</h2>
      <p class="text-gray-600 mb-8">{LOREM_SHORT}</p>
      <div class="space-y-4">
        <p class="flex items-center gap-3 text-gray-600"><span class="text-gray-900 font-medium">📧</span> hello@example.com</p>
        <p class="flex items-center gap-3 text-gray-600"><span class="text-gray-900 font-medium">📍</span> 123 Street, City, Country</p>
        <p class="flex items-center gap-3 text-gray-600"><span class="text-gray-900 font-medium">📞</span> +1 234 567 890</p>
      </div>
    </div>
    <form class="space-y-4">
      <div class="grid grid-cols-2 gap-4">
        <div><label class="block text-sm font-medium text-gray-700 mb-1">First name</label><input type="text" class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-black"></div>
        <div><label class="block text-sm font-medium text-gray-700 mb-1">Last name</label><input type="text" class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-black"></div>
      </div>
      <div><label class="block text-sm font-medium text-gray-700 mb-1">Email</label><input type="email" class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-black"></div>
      <div><label class="block text-sm font-medium text-gray-700 mb-1">Message</label><textarea rows="4" class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-black"></textarea></div>
      {make_button("Send message")}
    </form>
  </div>
</section>
"""
    return f"""
<section class="bg-white py-16 md:py-24">
  <div class="container mx-auto px-6 max-w-xl text-center">
    <p class="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Contact</p>
    <h2 class="text-3xl font-bold text-gray-900 mb-4">Get in touch</h2>
    <p class="text-gray-600 mb-8">{LOREM_SHORT}</p>
    <form class="space-y-4 text-left">
      <div><label class="block text-sm font-medium text-gray-700 mb-1">Email</label><input type="email" class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-black"></div>
      <div><label class="block text-sm font-medium text-gray-700 mb-1">Message</label><textarea rows="4" class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-black"></textarea></div>
      <div class="text-center">{make_button("Send message")}</div>
    </form>
  </div>
</section>
"""


@register(["cta", "banners"])
def build_cta(name, category, node_id):
    is_dark = "dark" in name.lower()
    bg = "bg-black" if is_dark else "bg-gray-50"
    text = "text-white" if is_dark else "text-gray-900"
    sub = "text-gray-400" if is_dark else "text-gray-600"
    return f"""
<section class="{bg} py-16 md:py-24">
  <div class="container mx-auto px-6 text-center max-w-2xl">
    <h2 class="text-3xl md:text-4xl font-bold {text} mb-4">Short heading here</h2>
    <p class="text-lg {sub} mb-8">{LOREM_SHORT}</p>
    <div class="flex items-center justify-center gap-4 flex-wrap">
      {make_button("Get started")}
      {make_button("Learn more", "secondary")}
    </div>
  </div>
</section>
"""


@register(["gallery"])
def build_gallery(name, category, node_id):
    return f"""
<section class="bg-white py-16 md:py-24">
  <div class="container mx-auto px-6">
    <div class="text-center mb-12">
      <h2 class="text-3xl font-bold text-gray-900 mb-4">Gallery</h2>
      <p class="text-gray-600">{LOREM_SHORT}</p>
    </div>
    <div class="grid grid-cols-2 md:grid-cols-3 gap-4">
      {"".join([f'<div class="aspect-square bg-gray-200 rounded-lg flex items-center justify-center"><span class="text-gray-400 text-sm">Image {i+1}</span></div>' for i in range(6)])}
    </div>
  </div>
</section>
"""


@register(["blog-sections", "blog-headers", "blog-pages", "blog-post-headers", "blog-post-pages"])
def build_blog(name, category, node_id):
    return f"""
<section class="bg-white py-16 md:py-24">
  <div class="container mx-auto px-6">
    <div class="text-center mb-12">
      <p class="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Blog</p>
      <h2 class="text-3xl md:text-4xl font-bold text-gray-900 mb-4">Latest articles</h2>
      <p class="text-gray-600 max-w-xl mx-auto">{LOREM_SHORT}</p>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-8">
      {"".join([f'''
      <article class="group">
        <div class="aspect-video bg-gray-200 rounded-lg mb-4 flex items-center justify-center"><span class="text-gray-400 text-sm">Image {i+1}</span></div>
        <p class="text-xs text-gray-500 mb-2">Category · 5 min read</p>
        <h3 class="font-bold text-gray-900 mb-2 group-hover:text-gray-600 transition-colors">Blog post title heading goes here</h3>
        <p class="text-sm text-gray-600 mb-4">{LOREM_SHORT}</p>
        <div class="flex items-center gap-3">
          <div class="w-8 h-8 bg-gray-200 rounded-full"></div>
          <div><p class="text-sm font-medium text-gray-900">Author Name</p><p class="text-xs text-gray-500">Jan 1, 2025</p></div>
        </div>
      </article>''' for i in range(3)])}
    </div>
  </div>
</section>
"""


@register(["stats-sections", "stat-cards"])
def build_stats(name, category, node_id):
    return f"""
<section class="bg-white py-16 md:py-24">
  <div class="container mx-auto px-6">
    <div class="grid grid-cols-2 md:grid-cols-4 gap-8">
      {"".join([f'''
      <div class="text-center">
        <p class="text-4xl md:text-5xl font-bold text-gray-900 mb-2">{num}%</p>
        <p class="text-gray-500 text-sm">Metric label goes here</p>
      </div>''' for num in ["80", "65", "95", "40"]])}
    </div>
  </div>
</section>
"""


@register(["testimonials", "logos"])
def build_logos(name, category, node_id):
    return f"""
<section class="bg-gray-50 py-12">
  <div class="container mx-auto px-6">
    <p class="text-center text-sm text-gray-400 uppercase tracking-widest mb-8">Trusted by leading companies</p>
    <div class="flex flex-wrap items-center justify-center gap-8 md:gap-16">
      {"".join([f'<div class="h-8 w-24 bg-gray-200 rounded flex items-center justify-center"><span class="text-gray-400 text-xs">Logo {i+1}</span></div>' for i in range(6)])}
    </div>
  </div>
</section>
"""


@register(["timelines"])
def build_timeline(name, category, node_id):
    return f"""
<section class="bg-white py-16 md:py-24">
  <div class="container mx-auto px-6 max-w-3xl">
    <div class="text-center mb-12">
      <h2 class="text-3xl font-bold text-gray-900 mb-4">Our journey</h2>
    </div>
    <div class="relative border-l border-gray-200 ml-4 space-y-10">
      {"".join([f'''
      <div class="relative pl-8">
        <div class="absolute -left-2.5 top-1 w-5 h-5 bg-black rounded-full border-4 border-white"></div>
        <p class="text-sm font-semibold text-gray-500 mb-1">202{i}</p>
        <h3 class="font-bold text-gray-900 mb-2">Milestone {i+1}</h3>
        <p class="text-gray-600 text-sm">{LOREM_SHORT}</p>
      </div>''' for i in range(4)])}
    </div>
  </div>
</section>
"""


@register(["forms", "multi-step-forms", "onboarding-forms"])
def build_form(name, category, node_id):
    return f"""
<section class="bg-white py-16 md:py-24">
  <div class="container mx-auto px-6 max-w-lg">
    <div class="text-center mb-8">
      <h2 class="text-3xl font-bold text-gray-900 mb-3">Short heading here</h2>
      <p class="text-gray-600">{LOREM_SHORT}</p>
    </div>
    <form class="space-y-4 bg-white border border-gray-200 rounded-xl p-8">
      <div class="grid grid-cols-2 gap-4">
        <div><label class="block text-sm font-medium text-gray-700 mb-1">First name</label><input type="text" placeholder="John" class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-black"></div>
        <div><label class="block text-sm font-medium text-gray-700 mb-1">Last name</label><input type="text" placeholder="Doe" class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-black"></div>
      </div>
      <div><label class="block text-sm font-medium text-gray-700 mb-1">Email</label><input type="email" placeholder="hello@example.com" class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-black"></div>
      <div><label class="block text-sm font-medium text-gray-700 mb-1">Company</label><input type="text" placeholder="Acme Inc." class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-black"></div>
      <div><label class="block text-sm font-medium text-gray-700 mb-1">Message</label><textarea rows="3" placeholder="How can we help?" class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-black"></textarea></div>
      <div class="flex items-start gap-2">
        <input type="checkbox" id="consent" class="mt-1">
        <label for="consent" class="text-xs text-gray-500">I agree to the <a href="#" class="underline">privacy policy</a> and <a href="#" class="underline">terms</a>.</label>
      </div>
      <div>{make_button("Submit")}</div>
    </form>
  </div>
</section>
"""


@register(["sign-up-and-log-in-pages", "sign-up-and-log-in-modals"])
def build_auth(name, category, node_id):
    is_signup = "sign up" in name.lower() or "signup" in name.lower() or "register" in name.lower()
    title = "Create an account" if is_signup else "Log in to your account"
    return f"""
<section class="bg-gray-50 min-h-screen flex items-center justify-center py-12 px-4">
  <div class="w-full max-w-md bg-white border border-gray-200 rounded-xl p-8">
    <div class="text-center mb-8">
      <div class="text-2xl font-bold text-gray-900 mb-1">Brand</div>
      <h1 class="text-xl font-bold text-gray-900">{title}</h1>
      <p class="text-sm text-gray-500 mt-1">{"Already have an account? <a href='#' class='underline'>Log in</a>" if is_signup else "Don't have an account? <a href='#' class='underline'>Sign up</a>"}</p>
    </div>
    <form class="space-y-4">
      {"<div><label class='block text-sm font-medium text-gray-700 mb-1'>Name</label><input type='text' class='w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-black'></div>" if is_signup else ""}
      <div><label class="block text-sm font-medium text-gray-700 mb-1">Email</label><input type="email" class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-black"></div>
      <div><label class="block text-sm font-medium text-gray-700 mb-1">Password</label><input type="password" class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-black"></div>
      <div>{make_button("Continue")}</div>
    </form>
    <div class="mt-6 relative">
      <div class="absolute inset-0 flex items-center"><div class="w-full border-t border-gray-200"></div></div>
      <div class="relative flex justify-center text-xs text-gray-400"><span class="bg-white px-2">or continue with</span></div>
    </div>
    <div class="mt-4 grid grid-cols-2 gap-3">
      {make_button("Google", "secondary")}
      {make_button("GitHub", "secondary")}
    </div>
  </div>
</section>
"""


@register(["tables"])
def build_table(name, category, node_id):
    return f"""
<section class="bg-white py-16">
  <div class="container mx-auto px-6">
    <div class="mb-6 flex items-center justify-between">
      <h2 class="text-xl font-bold text-gray-900">Data table</h2>
      {make_button("Add item")}
    </div>
    <div class="overflow-x-auto border border-gray-200 rounded-xl">
      <table class="w-full text-sm">
        <thead class="bg-gray-50 border-b border-gray-200">
          <tr>
            <th class="px-4 py-3 text-left font-semibold text-gray-700">Name</th>
            <th class="px-4 py-3 text-left font-semibold text-gray-700">Status</th>
            <th class="px-4 py-3 text-left font-semibold text-gray-700">Date</th>
            <th class="px-4 py-3 text-left font-semibold text-gray-700">Amount</th>
            <th class="px-4 py-3 text-right font-semibold text-gray-700">Actions</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100">
          {"".join([f'''
          <tr class="hover:bg-gray-50">
            <td class="px-4 py-3 font-medium text-gray-900">Item {i+1}</td>
            <td class="px-4 py-3"><span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">Active</span></td>
            <td class="px-4 py-3 text-gray-500">Jan {i+1}, 2025</td>
            <td class="px-4 py-3 text-gray-900">€{(i+1)*25}.00</td>
            <td class="px-4 py-3 text-right"><button class="text-sm text-gray-500 hover:text-gray-900">Edit</button></td>
          </tr>''' for i in range(5)])}
        </tbody>
      </table>
    </div>
  </div>
</section>
"""


def build_generic(name, category, node_id):
    """Fallback voor categorieën zonder specifieke builder."""
    return f"""
<section class="bg-white py-16 md:py-24">
  <div class="container mx-auto px-6">
    <div class="max-w-2xl mx-auto text-center mb-12">
      <p class="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Section</p>
      <h2 class="text-3xl md:text-4xl font-bold text-gray-900 mb-4">Short heading here</h2>
      <p class="text-lg text-gray-600">{LOREM_SHORT}</p>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
      {"".join([f'''
      <div class="bg-gray-50 rounded-xl p-6">
        <div class="w-10 h-10 bg-gray-200 rounded-lg mb-4 flex items-center justify-center">
          <span class="text-gray-500 text-sm">{i+1}</span>
        </div>
        <h3 class="font-bold text-gray-900 mb-2">Item {i+1}</h3>
        <p class="text-gray-600 text-sm">{LOREM_SHORT}</p>
      </div>''' for i in range(3)])}
    </div>
  </div>
</section>
"""


def get_builder(category: str):
    return BUILDERS.get(category, build_generic)


def generate_html(component: dict) -> str:
    name = component["name"]
    page_name = component["page_name"]
    node_id = component["id"]
    category = page_to_category(page_name)

    builder = get_builder(category)
    body_html = builder(name, category, node_id)

    return (
        HTML_HEAD.format(
            title=f"{name} — {category}",
            name=name,
            category=category,
            node_id=node_id,
        )
        + body_html
        + HTML_FOOT
    )


def main():
    with open(COMPONENTS_RAW, encoding="utf-8") as f:
        data = json.load(f)

    components = data["components"]
    print(f"Genereren van {len(components)} componenten...")

    index = []
    written = 0
    skipped = 0

    # Count per category for naming collisions
    cat_name_counts: dict = {}

    for comp in components:
        name = comp["name"]
        page_name = comp["page_name"]
        node_id = comp["id"]
        category = page_to_category(page_name)

        slug = slugify(name)
        if not slug:
            slug = f"component-{node_id.replace(':', '-')}"

        # Handle duplicates within category
        key = (category, slug)
        cat_name_counts[key] = cat_name_counts.get(key, 0) + 1
        count = cat_name_counts[key]
        if count > 1:
            final_slug = f"{slug}-{count}"
        else:
            final_slug = slug

        out_path = OUT_DIR / category / f"{final_slug}.html"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            html = generate_html(comp)
            out_path.write_text(html, encoding="utf-8")
            written += 1
        except Exception as e:
            print(f"  ⚠ Fout bij {name}: {e}", file=sys.stderr)
            skipped += 1
            continue

        index.append({
            "id": node_id,
            "name": name,
            "category": category,
            "file": f"components/{category}/{final_slug}.html",
            "description": describe_component(name, category),
            "tags": tags_for(name, category),
        })

    INDEX_PATH.write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"\n✅ Geschreven: {written} componenten")
    print(f"⚠  Overgeslagen: {skipped}")
    print(f"📁 Output: {OUT_DIR}")
    print(f"📋 Index: {INDEX_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
