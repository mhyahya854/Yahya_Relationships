export interface OptionItem<T extends string = string> {
  value: T;
  label: string;
}

export const PARENT_KINDS: readonly OptionItem[] = [
  { value: "biological", label: "Biological" },
  { value: "adopted", label: "Adopted" },
  { value: "step", label: "Step" },
  { value: "foster", label: "Foster" },
  { value: "guardian", label: "Guardian" },
  { value: "unknown", label: "Unknown" },
  { value: "unspecified", label: "Unspecified" },
] as const;

export const PARENT_ROLES: readonly OptionItem[] = [
  { value: "father", label: "Father" },
  { value: "mother", label: "Mother" },
  { value: "parent", label: "Parent (Unspecified gender)" },
  { value: "unknown", label: "Unknown" },
] as const;

export const MARRIAGE_STATUSES: readonly OptionItem[] = [
  { value: "married", label: "Married" },
  { value: "divorced", label: "Divorced" },
  { value: "widowed", label: "Widowed" },
  { value: "unknown", label: "Unknown" },
] as const;

export const MARRIAGE_CHILDREN_STATUSES: readonly OptionItem[] = [
  { value: "", label: "Unspecified / Has children" },
  { value: "no_children", label: "No Children" },
  { value: "unknown", label: "Unknown" },
] as const;

export const SIBLING_GROUP_TYPES: readonly OptionItem[] = [
  { value: "", label: "Default / General Sibling Group" },
  { value: "full", label: "Full Siblings" },
] as const;

export const GENERAL_TYPES: readonly OptionItem[] = [
  { value: "close_friend", label: "Close Friend" },
  { value: "friend", label: "Friend" },
  { value: "childhood_friend", label: "Childhood Friend" },
  { value: "best_friend", label: "Best Friend" },
  { value: "colleague", label: "Colleague" },
  { value: "former_colleague", label: "Former Colleague" },
  { value: "neighbour", label: "Neighbour" },
  { value: "acquaintance", label: "Acquaintance" },
  { value: "mentor", label: "Mentor / Mentee" },
  { value: "custom", label: "Custom Labels" },
] as const;
