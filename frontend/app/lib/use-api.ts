"use client";

import { useEffect, useState } from "react";
import { getJson } from "./api";

export function useApi<T>(path: string, refreshMs = 0) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [data, setData] = useState<T | null>(null);

  useEffect(() => {
    let active = true;
    const load = () => {
      getJson<T>(path)
        .then((value) => {
          if (active) {
            setData(value);
            setError("");
            setLoading(false);
          }
        })
        .catch((reason: Error) => {
          if (active) {
            setError(reason.message);
            setLoading(false);
          }
        });
    };
    load();
    if (!refreshMs) return () => { active = false; };
    const timer = window.setInterval(load, refreshMs);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [path, refreshMs]);

  return { loading, error, data };
}
