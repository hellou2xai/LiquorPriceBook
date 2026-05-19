import PageStub from "../components/PageStub";
import { useAuth } from "../lib/auth";

export default function Dashboard() {
  const { username } = useAuth();
  return (
    <PageStub
      title="Dashboard"
      subtitle={`Welcome${username ? `, ${username}` : ""}. Latest price-book activity will appear here.`}
    >
      <div className="space-y-2">
        <p>The dashboard surfaces three things once data is ingested:</p>
        <ul className="list-disc pl-5 space-y-1">
          <li>What moved this month (top price changes against the prior edition)</li>
          <li>Your watchlist top movers</li>
          <li>Recent alerts and unread anomaly findings</li>
        </ul>
      </div>
    </PageStub>
  );
}
