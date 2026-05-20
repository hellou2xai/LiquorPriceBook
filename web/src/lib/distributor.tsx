import { createContext, useContext, useState, useEffect, type ReactNode } from "react";

type Dist = { slug: string; label: string };

const DISTRIBUTORS: Dist[] = [
  { slug: "nj-allied", label: "Allied" },
  { slug: "nj-fedway", label: "Fedway" },
];

type DistCtx = {
  distributor: string;
  distributorLabel: string;
  setDistributor: (slug: string) => void;
  distributors: Dist[];
};

const DistributorContext = createContext<DistCtx>({
  distributor: "nj-allied",
  distributorLabel: "Allied",
  setDistributor: () => {},
  distributors: DISTRIBUTORS,
});

export function DistributorProvider({ children }: { children: ReactNode }) {
  const [slug, setSlug] = useState(() => localStorage.getItem("lpb_distributor") || "nj-allied");

  useEffect(() => {
    localStorage.setItem("lpb_distributor", slug);
  }, [slug]);

  const label = DISTRIBUTORS.find((d) => d.slug === slug)?.label ?? slug;

  return (
    <DistributorContext.Provider
      value={{ distributor: slug, distributorLabel: label, setDistributor: setSlug, distributors: DISTRIBUTORS }}
    >
      {children}
    </DistributorContext.Provider>
  );
}

export function useDistributor() {
  return useContext(DistributorContext);
}
