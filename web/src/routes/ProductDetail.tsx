import { useParams } from "react-router-dom";

import PageStub from "../components/PageStub";

export default function ProductDetail() {
  const { code } = useParams<{ code: string }>();
  return (
    <PageStub
      title={`Product ${code ?? ""}`}
      subtitle="Price history, RIP timeline, partials calendar, buy-now-vs-defer verdict and notes."
    />
  );
}
