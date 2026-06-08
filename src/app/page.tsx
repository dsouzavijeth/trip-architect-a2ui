import { redirect } from "next/navigation";

// The app is the trip architect; send the root straight there.
export default function Home() {
  redirect("/trip");
}
