export type Contact = {
  name: string;
  title: string;
  email: string;
  photo: string;
};

export type ClientRecord = {
  id: string;
  name: string;
  industry: string;
  region: string;
  plan: string;
  arr: number;
  seats: number;
  renewal: string;
  since: string;
  owner: string;
  billingEmail: string;
  health: "Healthy" | "Watch" | "At risk";
  logo: string;
  cover: string;
  contacts: Contact[];
};

export type Invoice = {
  id: string;
  clientId: string;
  period: string;
  amount: number;
  status: "Paid" | "Due" | "Overdue";
};

export const TEAM = [
  {
    name: "Priya Mehta",
    role: "Revenue ops",
    photo: "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&fit=crop&w=200&h=200&q=80",
  },
  {
    name: "James Okonkwo",
    role: "CSM lead",
    photo: "https://images.unsplash.com/photo-1560250097-0b93528c311a?auto=format&fit=crop&w=200&h=200&q=80",
  },
  {
    name: "Elena Voss",
    role: "Billing",
    photo: "https://images.unsplash.com/photo-1580489944761-15a19d654956?auto=format&fit=crop&w=200&h=200&q=80",
  },
];

/** Simulated private CRM / billing DB — never meant for proprietary cloud models. */
export const CLIENTS: ClientRecord[] = [
  {
    id: "CLT-1042",
    name: "Harborline Logistics",
    industry: "Supply chain",
    region: "North America",
    plan: "Enterprise",
    arr: 840000,
    seats: 220,
    renewal: "2026-11-14",
    since: "2022",
    owner: "James Okonkwo",
    billingEmail: "ap@harborline.example",
    health: "Healthy",
    logo: "https://images.unsplash.com/photo-1560179707-f14eea88fc6d?auto=format&fit=crop&w=120&h=120&q=80",
    cover: "https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?auto=format&fit=crop&w=1200&h=400&q=80",
    contacts: [
      {
        name: "Dana Ruiz",
        title: "VP Operations",
        email: "dana.ruiz@harborline.example",
        photo: "https://images.unsplash.com/photo-1438761681033-6461ffad8d80?auto=format&fit=crop&w=120&h=120&q=80",
      },
      {
        name: "Owen Blake",
        title: "Finance controller",
        email: "owen.blake@harborline.example",
        photo: "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=120&h=120&q=80",
      },
    ],
  },
  {
    id: "CLT-1108",
    name: "Northstar Clinics",
    industry: "Healthcare",
    region: "North America",
    plan: "Enterprise+",
    arr: 1260000,
    seats: 480,
    renewal: "2026-08-01",
    since: "2021",
    owner: "Priya Mehta",
    billingEmail: "billing@northstar-clinics.example",
    health: "Watch",
    logo: "https://images.unsplash.com/photo-1519494026892-80bbd2d6fd0d?auto=format&fit=crop&w=120&h=120&q=80",
    cover: "https://images.unsplash.com/photo-1516549655169-df83a0774514?auto=format&fit=crop&w=1200&h=400&q=80",
    contacts: [
      {
        name: "Dr. Leah Kim",
        title: "CIO",
        email: "l.kim@northstar-clinics.example",
        photo: "https://images.unsplash.com/photo-1559839734-2b71ea197ec2?auto=format&fit=crop&w=120&h=120&q=80",
      },
      {
        name: "Marcus Hale",
        title: "Procurement",
        email: "m.hale@northstar-clinics.example",
        photo: "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=120&h=120&q=80",
      },
    ],
  },
  {
    id: "CLT-1175",
    name: "Velvet & Co.",
    industry: "Retail",
    region: "Europe",
    plan: "Growth",
    arr: 312000,
    seats: 64,
    renewal: "2026-09-30",
    since: "2023",
    owner: "Elena Voss",
    billingEmail: "accounts@velvetco.example",
    health: "At risk",
    logo: "https://images.unsplash.com/photo-1441986300917-64674bd600d8?auto=format&fit=crop&w=120&h=120&q=80",
    cover: "https://images.unsplash.com/photo-1441984904996-e0b6ba687e04?auto=format&fit=crop&w=1200&h=400&q=80",
    contacts: [
      {
        name: "Inès Moreau",
        title: "Head of Digital",
        email: "ines.moreau@velvetco.example",
        photo: "https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&w=120&h=120&q=80",
      },
    ],
  },
  {
    id: "CLT-1219",
    name: "Brightfield Energy",
    industry: "Energy",
    region: "Europe",
    plan: "Enterprise",
    arr: 990000,
    seats: 310,
    renewal: "2027-01-12",
    since: "2020",
    owner: "James Okonkwo",
    billingEmail: "payables@brightfield.example",
    health: "Healthy",
    logo: "https://images.unsplash.com/photo-1473341304170-971dccb5ac1e?auto=format&fit=crop&w=120&h=120&q=80",
    cover: "https://images.unsplash.com/photo-1466611653911-95081537e5b7?auto=format&fit=crop&w=1200&h=400&q=80",
    contacts: [
      {
        name: "Tomás Silva",
        title: "CFO office",
        email: "t.silva@brightfield.example",
        photo: "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?auto=format&fit=crop&w=120&h=120&q=80",
      },
      {
        name: "Anya Petrov",
        title: "IT security",
        email: "a.petrov@brightfield.example",
        photo: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=120&h=120&q=80",
      },
    ],
  },
  {
    id: "CLT-1284",
    name: "Sakura Payments",
    industry: "Fintech",
    region: "APAC",
    plan: "Enterprise+",
    arr: 1540000,
    seats: 190,
    renewal: "2026-12-01",
    since: "2019",
    owner: "Priya Mehta",
    billingEmail: "finance@sakura-pay.example",
    health: "Healthy",
    logo: "https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?auto=format&fit=crop&w=120&h=120&q=80",
    cover: "https://images.unsplash.com/photo-1553729459-efe14ef6055d?auto=format&fit=crop&w=1200&h=400&q=80",
    contacts: [
      {
        name: "Yuki Tanaka",
        title: "Head of Platform",
        email: "y.tanaka@sakura-pay.example",
        photo: "https://images.unsplash.com/photo-1580489944761-15a19d654956?auto=format&fit=crop&w=120&h=120&q=80",
      },
    ],
  },
  {
    id: "CLT-1301",
    name: "CivicGrid Municipal",
    industry: "Public sector",
    region: "North America",
    plan: "Gov",
    arr: 560000,
    seats: 140,
    renewal: "2026-07-15",
    since: "2024",
    owner: "Elena Voss",
    billingEmail: "treasury@civicgrid.example",
    health: "Watch",
    logo: "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=120&h=120&q=80",
    cover: "https://images.unsplash.com/photo-1449824913935-59a10b8d2000?auto=format&fit=crop&w=1200&h=400&q=80",
    contacts: [
      {
        name: "Helen Carter",
        title: "Program director",
        email: "h.carter@civicgrid.example",
        photo: "https://images.unsplash.com/photo-1573497019940-1c28c88b4f3e?auto=format&fit=crop&w=120&h=120&q=80",
      },
    ],
  },
];

export const INVOICES: Invoice[] = [
  { id: "INV-9021", clientId: "CLT-1042", period: "2026-Q2", amount: 210000, status: "Paid" },
  { id: "INV-9088", clientId: "CLT-1042", period: "2026-Q3", amount: 210000, status: "Due" },
  { id: "INV-8870", clientId: "CLT-1108", period: "2026-Q2", amount: 315000, status: "Paid" },
  { id: "INV-9112", clientId: "CLT-1108", period: "2026-Q3", amount: 315000, status: "Overdue" },
  { id: "INV-9004", clientId: "CLT-1175", period: "2026-Q2", amount: 78000, status: "Overdue" },
  { id: "INV-9130", clientId: "CLT-1175", period: "2026-Q3", amount: 78000, status: "Due" },
  { id: "INV-8955", clientId: "CLT-1219", period: "2026-Q2", amount: 247500, status: "Paid" },
  { id: "INV-9144", clientId: "CLT-1219", period: "2026-Q3", amount: 247500, status: "Due" },
  { id: "INV-9010", clientId: "CLT-1284", period: "2026-Q2", amount: 385000, status: "Paid" },
  { id: "INV-9151", clientId: "CLT-1284", period: "2026-Q3", amount: 385000, status: "Paid" },
  { id: "INV-9066", clientId: "CLT-1301", period: "2026-Q2", amount: 140000, status: "Paid" },
  { id: "INV-9160", clientId: "CLT-1301", period: "2026-Q3", amount: 140000, status: "Due" },
];

export const REVENUE_BY_MONTH = [
  { month: "Feb", amount: 412000 },
  { month: "Mar", amount: 438000 },
  { month: "Apr", amount: 451000 },
  { month: "May", amount: 469000 },
  { month: "Jun", amount: 482000 },
  { month: "Jul", amount: 505000 },
];
