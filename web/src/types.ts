// The page's types. They're made from the server's JSON schemas, so the two
// can't drift apart: see scripts/types.mjs.
export type { Choice, Choices, Groups, Item, Need, Output, Plugin, Settings, Status } from "./types.gen";
import type { Groups } from "./types.gen";

export type Group = Groups[number];
