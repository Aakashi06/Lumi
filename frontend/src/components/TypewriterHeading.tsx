import { useEffect, useState } from "react";
import { useReducedMotion } from "motion/react";

const phrase = "Make space for curiosity.";

export default function TypewriterHeading() {
  const reduced = useReducedMotion();
  const [length, setLength] = useState(0);
  useEffect(() => {
    if (reduced) return;
    const timer = window.setInterval(() => {
      setLength((value) => {
        if (value + 1 >= phrase.length) window.clearInterval(timer);
        return Math.min(value + 1, phrase.length);
      });
    }, 65);
    return () => window.clearInterval(timer);
  }, [reduced]);
  const visible = reduced ? phrase.length : length;
  return (
    <h1 className="typewriter-heading" aria-label={phrase}>
      <span className="typewriter-space" aria-hidden="true">
        Make space
        <br />
        for <em>curiosity.</em>
      </span>
      <span className="typewriter-text" aria-hidden="true">
        {phrase.slice(0, Math.min(visible, 10))}
        <br />
        {phrase.slice(11, Math.min(visible, 15))}
        <em>{phrase.slice(15, visible)}</em>
        {!reduced && visible < phrase.length && (
          <span className="typing-cursor" />
        )}
      </span>
    </h1>
  );
}
