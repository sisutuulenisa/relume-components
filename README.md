# Relume Component Library

HTML + Tailwind CSS componenten geëxtraheerd uit de Relume Figma Kit v3.7.
Automatisch gegenereerd via de Figma API. Elke component is een standalone HTML bestand met Tailwind CDN.

**Totaal: 1754 componenten in 58 categorieën**

## Gebruik als AI-referentie

- `index.json` — manifest met naam, categorie, bestandspad, beschrijving en tags
- `components/<categorie>/<naam>.html` — standalone HTML bestanden
- Elke file heeft bovenaan een HTML comment: `<!-- Relume: NAME | Category: CAT -->`

## Categorieën

| Categorie | Componenten |
|-----------|-------------|
| about-pages | 5 |
| application-shells | 16 |
| banners | 16 |
| blog-headers | 32 |
| blog-pages | 5 |
| blog-post-headers | 5 |
| blog-post-pages | 5 |
| blog-sections | 36 |
| card-headers | 2 |
| careers | 27 |
| category-filters | 6 |
| comparisons | 15 |
| contact | 30 |
| contact-modals | 6 |
| contact-pages | 5 |
| cookie-consent | 5 |
| cta-new | 67 |
| description-lists | 4 |
| event-headers | 6 |
| event-item-headers | 11 |
| event-sections | 37 |
| faq | 14 |
| features | 682 |
| footers | 17 |
| forms | 20 |
| gallery | 27 |
| grid-lists | 10 |
| headers | 27 |
| hero-headers-new | 130 |
| home-pages | 8 |
| legal-pages | 2 |
| links-pages | 16 |
| loaders | 5 |
| logos | 6 |
| long-form-content-sections | 32 |
| multi-step-forms | 46 |
| navbars | 32 |
| onboarding-forms | 17 |
| page-headers | 5 |
| portfolio-headers | 12 |
| portfolio-pages | 7 |
| portfolio-sections | 23 |
| pricing | 57 |
| pricing-pages | 5 |
| product-headers | 9 |
| product-list-sections | 12 |
| section-headers | 4 |
| sidebars | 15 |
| sign-up-and-log-in-modals | 5 |
| sign-up-and-log-in-pages | 17 |
| stacked-lists | 10 |
| stat-cards | 8 |
| stats-sections | 60 |
| style-guide | 8 |
| tables | 10 |
| team | 22 |
| timelines | 21 |
| topbars | 12 |

## Scripts

```bash
# Herontdek alle componenten (Figma API)
python3 scripts/01-explore.py
python3 scripts/02-discover.py

# Regenereer alle HTML bestanden
python3 scripts/03-extract.py
```

## Source

Figma file: [Relume Figma Kit v3.7](https://www.figma.com/design/csPgPVhduXpcjSAKHqsygR)
