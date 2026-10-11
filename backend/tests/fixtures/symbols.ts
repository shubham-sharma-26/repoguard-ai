import type { User } from "./user.js";

export function displayName(user: User): string {
  return user.name;
}

export class UserLabel {
  render(user: User): string {
    return displayName(user);
  }
}
