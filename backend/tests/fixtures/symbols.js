import { formatName } from "./format.js";

export function greet(name) {
  return formatName(name);
}

export const normalize = (value) => value.trim();

export class Greeter {
  constructor(prefix) {
    this.prefix = prefix;
  }

  say(name) {
    return `${this.prefix} ${name}`;
  }
}
