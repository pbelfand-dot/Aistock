export interface ColorVariant {
  id: string
  name: string
  hex: string
  bgGradient: string
  accentHex: string
}

export interface ProductFeature {
  icon: string
  label: string
}

export interface SizeRow {
  size: string
  col1: string
  col2?: string
  col3?: string
}

export interface ProductSpec {
  label: string
  value: string
}

export interface Product {
  id: string
  name: string
  subtitle: string
  tagline: string
  splitSlides: boolean // whether to show each color as its own slide
  colors: ColorVariant[]
  features: ProductFeature[]
  specs: ProductSpec[]
  materials: string[]
  construction: string[]
  sizeChart?: {
    headers: string[]
    rows: SizeRow[]
    fitNote: string
  }
  techBreakdown: { label: string; description: string }[]
  careIcons: string[]
}

export const COLORS: ColorVariant[] = [
  {
    id: 'black',
    name: 'Black',
    hex: '#111111',
    bgGradient: 'from-neutral-900 via-neutral-800 to-neutral-900',
    accentHex: '#ffffff',
  },
  {
    id: 'stone',
    name: 'Stone',
    hex: '#c4b89a',
    bgGradient: 'from-stone-300 via-stone-200 to-stone-300',
    accentHex: '#1a1a1a',
  },
  {
    id: 'sand',
    name: 'Sand',
    hex: '#c9a97a',
    bgGradient: 'from-amber-300 via-amber-200 to-amber-300',
    accentHex: '#1a1a1a',
  },
  {
    id: 'forest',
    name: 'Forest Green',
    hex: '#4a5c3a',
    bgGradient: 'from-green-900 via-green-800 to-green-900',
    accentHex: '#ffffff',
  },
  {
    id: 'charcoal',
    name: 'Charcoal',
    hex: '#3d3d3d',
    bgGradient: 'from-zinc-700 via-zinc-600 to-zinc-700',
    accentHex: '#ffffff',
  },
]

export const PRODUCTS: Product[] = [
  {
    id: 'chalk-bag',
    name: 'THE MATTERHORN CHALK BAG',
    subtitle: 'Chalk Bag',
    tagline: 'BUILT FOR MOVEMENT. DESIGNED FOR ELEVATION.',
    splitSlides: true,
    colors: COLORS,
    features: [
      { icon: '◈', label: 'Chalk Retention' },
      { icon: '❄', label: 'Fleece Lining' },
      { icon: '⊛', label: 'Drawstring Closure' },
      { icon: '⬡', label: 'Belt Loop' },
      { icon: '⚓', label: 'Carabiner Loop' },
    ],
    specs: [
      { label: 'Height', value: '18 CM / 7.1 IN' },
      { label: 'Diameter', value: '13 CM / 5.1 IN' },
      { label: 'Belt Length', value: '70 CM – 120 CM' },
    ],
    materials: [
      '100% Nylon (Outer) — Ripstop fabric for durability and abrasion resistance.',
      '100% Polyester (Lining) — Soft fleece lining for maximum chalk retention.',
    ],
    construction: [
      'Ripstop nylon exterior',
      'Fleece lined interior',
      'Drawstring closure',
      'Adjustable belt with buckle',
      'Belt loop & carabiner loop',
      'Hidden zip pocket',
      'Woven CRUXED label',
    ],
    techBreakdown: [
      { label: 'SOFT FLEECE LINING', description: 'For superior chalk retention.' },
      { label: 'DRAWSTRING CLOSURE', description: 'Secure and easy one-hand cinch.' },
      { label: 'ABSTRACT GRAPHIC', description: 'Matterhorn elevation print.' },
      { label: 'DURABLE BASE', description: 'Reinforced for long-lasting use.' },
      { label: 'BELT LOOP', description: 'Attach to harness or belt.' },
      { label: 'CARABINER LOOP', description: 'Clip in, chalk up, send.' },
      { label: 'ZIP POCKET', description: 'Hidden pocket for small essentials.' },
      { label: 'WOVEN LABEL', description: 'Signature CRUXED label.' },
    ],
    careIcons: ['Hand wash cold', 'Do not bleach', 'Do not tumble dry', 'Do not iron', 'Do not dry clean'],
  },
  {
    id: 'ridge-pants',
    name: 'THE MATTERHORN DROP RIDGE PANTS',
    subtitle: 'Ridge Pants',
    tagline: 'BUILT FOR MOVEMENT. DESIGNED FOR ELEVATION.',
    splitSlides: true,
    colors: COLORS,
    features: [
      { icon: '✦', label: '4-Way Stretch' },
      { icon: '◈', label: 'Water Resistant' },
      { icon: '❋', label: 'Breathable' },
      { icon: '⬡', label: 'Abstract Panels' },
      { icon: '⚙', label: 'Harness Compatible' },
    ],
    specs: [],
    sizeChart: {
      headers: ['SIZE', 'WAIST (IN)', 'HIP (IN)', 'INSEAM (IN)'],
      rows: [
        { size: 'S', col1: '28 – 30', col2: '36 – 38', col3: '30' },
        { size: 'M', col1: '30 – 32', col2: '38 – 40', col3: '30.5' },
        { size: 'L', col1: '32 – 34', col2: '40 – 42', col3: '31' },
        { size: 'XL', col1: '34 – 36', col2: '42 – 44', col3: '31.5' },
      ],
      fitNote: 'RELAXED / BAGGY FIT. SIZE DOWN FOR A MORE TAPERED LOOK.',
    },
    materials: [
      '90% Nylon — Lightweight, durable, and abrasion resistant.',
      '10% Spandex — 4-way stretch for unrestricted movement.',
      'DWR Coating — Durable water repellent finish to shed moisture.',
      'Ripstop Weave — Reinforced grid for enhanced durability.',
    ],
    construction: [
      'Triple-needle stitching for durability',
      'Gusseted crotch for increased mobility',
      'YKK® zippers throughout',
      'Reinforced stress points',
      'Breathable mesh pocketing',
      'Harness compatible design',
    ],
    techBreakdown: [
      { label: 'INTEGRATED BELT LOOP', description: 'Works with built-in webbing belt.' },
      { label: 'ADJUSTABLE DRAWCORD', description: 'Internal drawcord for custom comfort.' },
      { label: 'DEEP ZIP POCKETS', description: 'YKK® zippers for secure storage.' },
      { label: 'ABSTRACT PANELING', description: 'Engineered seams for durability and movement.' },
      { label: 'ARTICULATED KNEES', description: 'Pre-bent design for unrestricted mobility.' },
      { label: 'ZIP BACK POCKET', description: 'Hidden pocket for essentials.' },
      { label: 'GUSSETED CROTCH', description: 'Extra room for high steps and movement.' },
      { label: 'ADJUSTABLE CUFFS', description: 'Drawcords to cinch or wear open.' },
    ],
    careIcons: ['Machine wash cold', 'Do not bleach', 'Tumble dry low or hang dry', 'Cool iron if needed', 'Do not dry clean'],
  },
  {
    id: 'ankle-sock',
    name: 'THE MATTERHORN DROP ANKLE SOCK',
    subtitle: 'Ankle Sock',
    tagline: 'BUILT FOR FRICTION. DESIGNED FOR CONTROL.',
    splitSlides: true,
    colors: COLORS,
    features: [
      { icon: '◈', label: 'Merino Wool Blend' },
      { icon: '⊛', label: 'Arch Compression' },
      { icon: '❋', label: 'Breathable Knit Zones' },
      { icon: '✦', label: 'Reinforced Heel & Toe' },
      { icon: '⬡', label: 'Low-Cut Fit' },
    ],
    specs: [],
    sizeChart: {
      headers: ['SIZE', 'US SHOE SIZE', 'UK', 'EU'],
      rows: [
        { size: 'S', col1: '4 – 6', col2: '3 – 5', col3: '36 – 38' },
        { size: 'M', col1: '6.5 – 8.5', col2: '5.5 – 7.5', col3: '39 – 42' },
        { size: 'L', col1: '9 – 11', col2: '8 – 10', col3: '43 – 45' },
        { size: 'XL', col1: '11.5 – 13', col2: '10.5 – 12', col3: '46 – 48' },
      ],
      fitNote: 'TRUE TO SIZE. SIZE UP FOR A RELAXED FIT.',
    },
    materials: [
      '45% Merino Wool — Temperature regulation, softness and odor resistance.',
      '35% Nylon — Durability and abrasion resistance.',
      '15% Polyester — Moisture wicking and quick drying.',
      '5% Elastane — Stretch and recovery for a performance fit.',
    ],
    construction: [
      'Seamless toe construction',
      'Y-heel for locked-in stability',
      'Arch compression band',
      'Reinforced heel and toe',
      'Breathable mesh ventilation',
      'Low-cut performance fit',
    ],
    techBreakdown: [
      { label: 'EMBROIDERED LOGO', description: 'Subtle detail. Premium finish.' },
      { label: 'KNIT MOUNTAIN ARTWORK', description: 'Inspired by the world\'s most iconic peak.' },
      { label: 'ARCH SUPPORT COMPRESSION', description: 'Targeted compression for a locked-in feel.' },
      { label: 'Y-HEEL CONSTRUCTION', description: 'Locks the heel in place for a secure fit.' },
      { label: 'BREATHABLE KNIT ZONES', description: 'Engineered airflow keeps feet cool and dry.' },
      { label: 'REINFORCED HEEL & TOE', description: 'Built to withstand friction, pressure, and repeated use.' },
    ],
    careIcons: ['Machine wash cold', 'Do not bleach', 'Tumble dry low or hang dry', 'Do not iron', 'Do not dry clean'],
  },
  {
    id: 'matterhorn-shirt',
    name: 'THE MATTERHORN SHIRT',
    subtitle: 'Technical Overshirt',
    tagline: 'BUILT FOR MOVEMENT. DESIGNED FOR ELEVATION.',
    splitSlides: false,
    colors: COLORS,
    features: [
      { icon: '✦', label: '4-Way Stretch' },
      { icon: '◈', label: 'Moisture Wicking' },
      { icon: '❋', label: 'Breathable' },
      { icon: '⊛', label: 'Abrasion Resistant' },
      { icon: '⬡', label: 'Utility Pocket' },
      { icon: '◈', label: 'Quick Dry' },
    ],
    specs: [],
    sizeChart: {
      headers: ['SIZE', 'CHEST (IN)', 'WAIST (IN)', 'SLEEVE (IN)'],
      rows: [
        { size: 'S', col1: '36 – 38', col2: '28 – 30', col3: '33 – 34' },
        { size: 'M', col1: '38 – 40', col2: '30 – 32', col3: '34 – 35' },
        { size: 'L', col1: '40 – 42', col2: '32 – 34', col3: '35 – 36' },
        { size: 'XL', col1: '42 – 44', col2: '34 – 36', col3: '36 – 37' },
        { size: 'XXL', col1: '44 – 46', col2: '36 – 38', col3: '37 – 38' },
      ],
      fitNote: 'TRUE TO SIZE. BUILT FOR PERFORMANCE. LAYER UP. MOVE FREELY.',
    },
    materials: [
      '90% Nylon — Lightweight, durable, and abrasion resistant.',
      '10% Spandex — 4-way stretch for unrestricted movement.',
      'Moisture wicking and quick dry.',
    ],
    construction: [
      'Triple-needle stitching for durability',
      'Reinforced seams in high-stress areas',
      'Back yoke with pleat for mobility',
      'Gusseted underarms for range of motion',
    ],
    techBreakdown: [
      { label: 'PERFORMANCE FABRIC', description: 'Lightweight, durable, and built to move.' },
      { label: '4-WAY STRETCH', description: 'Maximum mobility in every direction.' },
      { label: 'BREATHABLE', description: 'Moisture moves out, comfort stays in.' },
      { label: 'ABRASION RESISTANT', description: 'Built to withstand rugged conditions.' },
      { label: 'YKK® BUTTONS', description: 'Durable and secure closure.' },
      { label: 'UTILITY POCKET', description: 'Zippered chest pocket for essentials.' },
      { label: 'ARTICULATED CUT', description: 'Engineered for natural movement.' },
      { label: 'QUICK DRY', description: 'Dries fast to keep you comfortable.' },
    ],
    careIcons: ['Machine wash cold', 'Do not bleach', 'Tumble dry low or hang dry', 'Cool iron if needed', 'Do not dry clean'],
  },
]
