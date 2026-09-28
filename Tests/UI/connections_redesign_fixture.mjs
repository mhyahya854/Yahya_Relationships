/**
 * Deterministic, synthetic-only fixture for the Connections redesign.
 *
 * It is intentionally an API-level loader: callers start the application with
 * an isolated bootstrap, then this module creates a fresh data root and never
 * reads or writes the user's configured production root.
 */
import { execFileSync } from "node:child_process";
import { join } from "node:path";

const CORE_SPECS = [
  ["qadir", "Qadir Rahal", "male", 1912, ["قادر راحل"]],
  ["ilyana", "Ilyana Rahal", "female", 1916, ["الیانا"]],
  ["adnan", "Adnan Vale", "male", 1920, ["عدنان"]],
  ["soraya", "Soraya Vale", "female", 1923, ["ثریا"]],
  ["navid", "Navid Mehr", "male", 1918, []],
  ["mahira", "Mahira Mehr", "female", 1922, ["ماہرا"]],
  ["zohair", "Zohair Arden", "male", 1917, []],
  ["amara", "Amara Arden", "female", 1921, ["امارا"]],
  ["basim", "Basim Rahal", "male", 1938, ["باسم"]],
  ["nadia", "Nadia Sayeed", "female", 1941, ["نادیہ"]],
  ["pari", "Pari Mehr-Rahal", "female", 1943, ["پری"]],
  ["hamza", "Hamza Sayeed", "male", 1939, ["حمزہ"]],
  ["farah", "Farah Vale-Ito", "female", 1944, ["فرح"]],
  ["rafiq", "Rafiq Vale-Santos", "female", 1947, ["رفیقہ"]],
  ["tala", "Tala Ito", "male", 1942, []],
  ["noman", "Noman Santos", "male", 1945, ["نعمان"]],
  ["idris", "Idris Vale-Rahim", "male", 1962, []],
  ["kamal", "Kamal Vale-Noor", "male", 1965, []],
  ["salma", "Salma Rahal-Rahim", "female", 1964, ["سلمیٰ"]],
  ["layla", "Layla Sayeed-Noor", "female", 1967, ["لیلیٰ"]],
  ["nadim", "Nadim Rahal", "male", 1968, []],
  ["yasmin", "Yasmin Sayeed-Wu", "female", 1970, ["یاسمین"]],
  ["imran", "Imran Vale-Ito", "male", 1966, []],
  ["amal", "Amal Vale-Ito", "female", 1969, ["امل"]],
  ["danish", "Danish Vale-Santos", "male", 1971, ["دانش"]],
  ["safa", "Safa Vale-Santos", "female", 1974, []],
  ["katerina", "Katerina Volkov-Vale", "female", 1970, ["Kat"]],
  ["aaliyah", "Aaliyah Noor", "female", 1992, ["عالیہ"]],
  ["elias", "Elias Calder", "male", 1988, ["Eli"]],
  ["zayan", "Zayan Noor", "male", 1989, ["زیان"]],
  ["noor", "Noor Vale-Noor", "female", 1994, ["نور"]],
  ["leo", "Leo Volkov-Vale", "male", 1998, []],
  ["luna", "Luna Volkov", "female", 1995, ["Lulu"]],
  ["sebastian", "Sebastian Volkov", "male", 1968, []],
  ["hana", "Hana Calder-Rahim", "female", 2014, ["حنا"]],
  ["sami", "Sami Calder-Rahim", "male", 2017, ["سامی"]],
  ["rafi", "Rafi Noor", "male", 2015, ["رافع"]],
  ["nura", "Nura Noor", "female", 2018, ["نورا"]],
  ["anisa", "Anisa Rahal", "female", 1972, ["انیسہ"]],
  ["matea", "Matea Korić-Rahal", "female", 1971, ["Teja"]],
  ["soren", "Soren Rahal-Korić", "male", 2000, []],
  ["remi", "Remi Rahal-Korić", "unknown", 2003, ["ریمی"]],
  ["jun", "Jun Wu", "male", 1969, ["俊"]],
  ["aika", "Aika Sayeed-Wu", "female", 2001, []],
  ["teo", "Teo Sayeed-Wu", "male", 2005, []],
  ["darya", "Darya Sol — Community Orchestra Archivist", "female", 2011, ["دریا", "Dari"]],
  ["maeve", "Maeve Rowan", "female", 1982, []],
  ["kian", "Kian Moss", "male", 2012, ["کیان"]],
  ["oren", "Oren Moss", "male", 1980, []],
  ["sage", "Sage Bell", "unknown", 2010, ["سیج"]],
  ["quinn", "Quinn Aster", "unknown", 1979, []],
];

const EXTRA_SPECS = [
  ["raouf", "Raouf Rahal", "male", 1948, ["رؤف"]],
  ["samar", "Samar Rahal", "female", 1951, ["سمر"]],
  ["mariam", "Mariam Rahal", "female", 1975, ["مریم"]],
  ["karim", "Karim Rahal", "male", 1977, ["کریم"]],
  ["lena", "Lena Calder-Rahal", "female", 1976, []],
  ["mila", "Mila Rahal-Calder", "female", 2003, []],
  ["faris", "Faris Rahal", "male", 2005, ["فارس"]],
  ["hala", "Hala Noor-Rahal", "female", 1979, ["ہالہ"]],
  ["tamsin", "Tamsin Bell", "female", 1984, []],
  ["azhar", "Azhar Bell", "male", 1981, ["اظہر"]],
  ["leila", "Leila Moss", "female", 2006, []],
  ["murad", "Murad Moss", "male", 2008, ["مراد"]],
  ["naia", "Naia Sol", "female", 2010, []],
  ["hadi", "Hadi Sol", "male", 2012, ["ہادی"]],
  ["samira", "Samira Patel", "female", 1989, []],
  ["julian", "Julian Hart", "male", 1987, []],
  ["priya", "Priya Desai", "female", 1986, []],
  ["dev", "Dev Kapoor", "male", 1985, []],
  ["celine", "Celine Moreau", "female", 1990, []],
  ["nico", "Nico Reyes", "male", 1988, []],
  ["iris", "Iris Okafor", "female", 1991, []],
  ["pavel", "Pavel Novak", "male", 1983, []],
  ["zoe", "Zoe Bennett", "female", 1993, []],
  ["iman", "Iman Idris", "unknown", 1994, ["ایمان"]],
  ["rhea", "Rhea Santos", "female", 1992, []],
  ["ben", "Ben Calder", "male", 2013, []],
  ["kai", "Kai Calder", "unknown", 2016, []],
  ["uma", "Uma Wu", "female", 2011, []],
  ["yuri", "Yuri Wu", "male", 2013, []],
  ["ember", "Ember — Unresolved Synthetic Record", "unknown", null, []],
];

export const CONNECTIONS_FIXTURE_EXPECTED_PEOPLE = 82;

function role(people, key) {
  return people[key].gender === "male" ? "father" : people[key].gender === "female" ? "mother" : "parent";
}

function buildFamilyFixture(people) {
  const parentChild = [];
  const addChildren = (parents, children, kind = "biological") => {
    for (const child of children) for (const parent of parents) {
      parentChild.push({ parent: people[parent].id, child: people[child].id, role: role(people, parent), kind });
    }
  };
  addChildren(["qadir", "ilyana"], ["basim", "nadia", "raouf"]);
  addChildren(["adnan", "soraya"], ["idris", "kamal", "farah", "rafiq"]);
  addChildren(["navid", "mahira"], ["pari", "tala"]);
  addChildren(["zohair", "amara"], ["hamza", "noman"]);
  addChildren(["basim", "pari"], ["salma", "nadim", "anisa"]);
  addChildren(["nadia", "hamza"], ["layla", "yasmin"]);
  addChildren(["farah", "tala"], ["imran", "amal"]);
  addChildren(["rafiq", "noman"], ["danish", "safa"]);
  addChildren(["idris", "salma"], ["mira"]);
  addChildren(["kamal", "layla"], ["zayan", "noor"]);
  addChildren(["idris", "katerina"], ["leo"]);
  addChildren(["sebastian", "katerina"], ["luna"]);
  addChildren(["mira", "elias"], ["hana", "sami"]);
  addChildren(["zayan", "aaliyah"], ["rafi", "nura"]);
  addChildren(["nadim", "matea"], ["soren", "remi"]);
  addChildren(["yasmin", "jun"], ["aika", "teo"]);
  addChildren(["raouf", "samar"], ["mariam", "karim"]);
  addChildren(["mariam", "lena"], ["mila"]);
  addChildren(["karim", "hala"], ["faris"]);
  addChildren(["tamsin", "azhar"], ["leila", "murad"]);
  addChildren(["darya", "oren"], ["naia", "hadi"], "foster");
  addChildren(["mira", "elias"], ["ben"], "adopted");
  addChildren(["mira", "elias"], ["kai"], "guardian");
  addChildren(["jun", "yasmin"], ["uma", "yuri"], "step");
  parentChild.push(
    { parent: people.adnan.id, child: people.maeve.id, role: "father", kind: "biological" },
    { parent: people.pari.id, child: people.maeve.id, role: "mother", kind: "biological" },
    { parent: people.quinn.id, child: people.darya.id, role: "unknown", kind: "unknown" },
    { parent: people.quinn.id, child: people.ember.id, role: "unknown", kind: "unknown" },
    { parent: people.maeve.id, child: people.sage.id, role: "mother", kind: "guardian" },
  );

  const marriageSpecs = [
    ["qadir", "ilyana", "married", 1935], ["adnan", "soraya", "married", 1940],
    ["navid", "mahira", "widowed", 1941], ["zohair", "amara", "married", 1938],
    ["basim", "pari", "married", 1960], ["nadia", "hamza", "married", 1961],
    ["farah", "tala", "married", 1963], ["rafiq", "noman", "married", 1965],
    ["idris", "salma", "divorced", 1985], ["idris", "katerina", "married", 1996],
    ["katerina", "sebastian", "divorced", 1992], ["kamal", "layla", "married", 1987],
    ["mira", "elias", "married", 2012], ["zayan", "aaliyah", "married", 2013],
    ["nadim", "matea", "married", 1998], ["yasmin", "jun", "married", 1999],
    ["raouf", "samar", "married", 1972], ["mariam", "lena", "married", 2001],
    ["karim", "hala", "married", 2002], ["tamsin", "azhar", "married", 2004],
    ["darya", "oren", "unknown", 2009],
  ];
  const marriages = marriageSpecs.map(([first, second, status, year], display_order) => {
    const [spouse_a, spouse_b] = [people[first].id, people[second].id].sort();
    return { spouse_a, spouse_b, status, year, children_status: null, display_order };
  });
  const siblingSpecs = [
    ["basim", "nadia", "raouf"], ["idris", "kamal", "farah", "rafiq"],
    ["salma", "nadim", "anisa"], ["layla", "yasmin"], ["mira", "leo"],
    ["zayan", "noor"], ["hana", "sami", "ben", "kai"], ["rafi", "nura"],
    ["soren", "remi"], ["aika", "teo", "uma", "yuri"], ["mariam", "karim"],
    ["leila", "murad"], ["naia", "hadi"],
  ];
  const sibling_groups = siblingSpecs.map((members, index) => ({
    id: `connections_redesign_sibling_${String(index + 1).padStart(2, "0")}`,
    members: members.map((key) => people[key].id),
    ordered: true,
    type: members.length === 2 ? "full" : null,
    label_en: `Synthetic Connections sibling group ${index + 1}`,
    label_ur: null,
  }));
  return {
    expected_people: CONNECTIONS_FIXTURE_EXPECTED_PEOPLE,
    parent_child: parentChild,
    marriages,
    sibling_groups,
    multipath: { from: people.mira.id, to: people.maeve.id },
  };
}

async function writeJournal(api, person, content) {
  const current = await api(`/api/people/${person.id}/journal`);
  await api(`/api/people/${person.id}/journal`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, expected_exists: current.exists, expected_modified_ns: current.modified_ns, expected_sha256: current.sha256 }),
  });
}

export function drawerDemoFor(people) {
  return {
    [people.mira.id]: {
      memories: ["Synthetic memory: a 2018 orchard concert note.", "Synthetic memory: a mapped family-story interview."],
      events: ["Synthetic event: Connections design review, 2026-09-14."],
      media: ["Synthetic media metadata: orchard-rehearsal.jpg · fictional sample."],
      conversations: ["Synthetic conversation excerpt: ‘Confirm the two ancestry routes.’"],
      documents: ["Synthetic document: fictional field-notes.pdf."],
      places: ["Synthetic place: North Garden Archive · fictional only."],
    },
    [people.darya.id]: {
      memories: ["Synthetic memory: catalogued the community orchestra archive."],
      events: ["Synthetic event: rehearsal map check."],
      media: ["Synthetic media metadata: orchestra-ledger.png."],
      conversations: ["Synthetic conversation: archive volunteer handoff."],
      documents: ["Synthetic document: fictional programme notes."],
      places: ["Synthetic place: Riverside rehearsal room."],
    },
  };
}

export async function seedConnectionsRedesignFixture({ api, post, dataRoot, python, fixtureLoader, environment }) {
  const initialized = await post("/api/data-root/initialize", { target_path: dataRoot, owner_name: "Mira Rahim", owner_gender: "female" });
  const groupNames = [
    "Synthetic Friends & Community", "Synthetic Work Mentors", "Synthetic Heritage Circle",
    "Synthetic Neighbourhood Garden", "Synthetic International Branches", "Synthetic Archive Volunteers",
    "Synthetic Studio Colleagues", "Synthetic Travel Notes",
  ];
  const groups = {};
  for (const name of groupNames) groups[name] = (await post("/api/groups", { name })).group.id;
  const people = { mira: (await api(`/api/people/${initialized.owner_id}`)).person };
  const communityKeys = new Set(["darya", "maeve", "oren", "sage", "quinn", "tamsin", "azhar", "leila", "murad", "naia", "hadi", "samira", "julian", "priya", "dev", "celine", "nico", "iris", "pavel", "zoe", "iman", "rhea"]);
  for (const [key, name, gender, birth_year, aliases] of [...CORE_SPECS, ...EXTRA_SPECS]) {
    const group_ids = communityKeys.has(key)
      ? [groups["Synthetic Friends & Community"], groups["Synthetic Neighbourhood Garden"], ...(key.length % 3 === 0 ? [groups["Synthetic Archive Volunteers"]] : [])]
      : ["family", groups["Synthetic Heritage Circle"], ...(key.length % 4 === 0 ? [groups["Synthetic International Branches"]] : [])];
    people[key] = (await post("/api/people", {
      name, gender, birth_year, aliases, group_ids, primary_group_id: group_ids[0],
      note_en: `Synthetic Connections fixture record for ${name}.`,
      note_ur: aliases.some((alias) => /[\u0600-\u06ff]/.test(alias)) ? "یہ مکمل طور پر مصنوعی Connections ٹیسٹ مواد ہے۔" : undefined,
    })).person;
  }
  if (Object.keys(people).length !== CONNECTIONS_FIXTURE_EXPECTED_PEOPLE) {
    throw new Error(`Expected ${CONNECTIONS_FIXTURE_EXPECTED_PEOPLE} synthetic people; got ${Object.keys(people).length}.`);
  }

  const familyFacts = buildFamilyFixture(people);
  const certification = JSON.parse(execFileSync(
    python,
    [fixtureLoader, join(dataRoot, "Database", "relationships.db")],
    {
      input: JSON.stringify(familyFacts),
      encoding: "utf8",
      env: { ...environment, PEOPLE_RELATIONSHIPS_ROOT: dataRoot },
    },
  ).trim());
  if (certification.people !== CONNECTIONS_FIXTURE_EXPECTED_PEOPLE) throw new Error("Canonical synthetic fixture certification count mismatch.");

  const symmetric = [
    ["mira", "darya", "close_friend"], ["mira", "quinn", "childhood_friend"],
    ["mira", "yasmin", "best_friend"], ["mira", "anisa", "friend"],
    ["mira", "samira", "former_friend"], ["mira", "nico", "enemy"],
    ["mira", "priya", "former_colleague"], ["mira", "iris", "neighbour"],
    ["mira", "celine", "acquaintance"], ["darya", "mariam", "colleague"],
    ["darya", "safa", "close_friend"], ["elias", "imran", "colleague"],
    ["salma", "maeve", "former_colleague"], ["hana", "aika", "acquaintance"],
    ["zayan", "danish", "neighbour"], ["noor", "soren", "friend"],
    ["leo", "teo", "colleague"], ["remi", "sage", "best_friend"],
    ["samira", "julian", "friend"], ["julian", "priya", "colleague"],
    ["priya", "dev", "former_colleague"], ["dev", "celine", "acquaintance"],
    ["celine", "nico", "enemy"], ["iris", "zoe", "close_friend"],
    ["pavel", "iman", "neighbour"], ["rhea", "zoe", "childhood_friend"],
  ];
  for (const [first, second, type] of symmetric) {
    await post("/api/relationships/general", { person_a: people[first].id, person_b: people[second].id, type, directionality: "symmetric", notes: "Synthetic-only relationship used for Connections layout and route QA." });
  }
  const directional = [
    ["qadir", "basim", "mentor", "Family-history mentor", "Mentee"],
    ["mira", "sage", "mentor", "Writing mentor", "Mentee"],
    ["maeve", "darya", "mentee", "Archive mentee", "Archive coach"],
    ["oren", "quinn", "custom", "Coordinates the night garden", "Shares seed records"],
    ["aaliyah", "hana", "custom", "Language-practice guide", "Practice partner"],
  ];
  for (const [first, second, type, forward, reverse] of directional) {
    await post("/api/relationships/general", { person_a: people[first].id, person_b: people[second].id, type, directionality: "directional", label_a_to_b: forward, label_b_to_a: reverse, notes: "Synthetic-only directional relationship; no transitive inference." });
  }
  for (const [key, groupName] of [["mira", "Synthetic Archive Volunteers"], ["darya", "Synthetic Archive Volunteers"], ["mariam", "Synthetic Travel Notes"], ["priya", "Synthetic Studio Colleagues"], ["dev", "Synthetic Studio Colleagues"]]) {
    await post(`/api/people/${people[key].id}/groups`, { group_id: groups[groupName], primary: false });
  }
  await writeJournal(api, people.mira, "# Mira's synthetic field notes\n\nEvery name and route in this fixture is fictional. The route review keeps family derivation separate from direct friendship facts.\n");
  await writeJournal(api, people.darya, "# Synthetic archive note\n\nA fictional rehearsal catalog and community route were prepared only for screenshot verification.\n");
  await writeJournal(api, people.mariam, "# Synthetic branch note\n\nThis child-parent branch is deliberately used to verify a mixed external and family route.\n");

  return { people, groups, certification, drawerDemo: drawerDemoFor(people) };
}
