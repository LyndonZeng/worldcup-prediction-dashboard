import {Dashboard} from "../components/Dashboard";
import {mockDashboardData} from "../lib/mock";

export default function Page() {
  return <Dashboard initialData={mockDashboardData} />;
}
