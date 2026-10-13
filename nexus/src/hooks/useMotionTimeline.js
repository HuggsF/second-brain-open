import { useEffect, useRef, useState } from 'react';
import { createMotionDriver, createMotionScheduler, EMPTY_MOTION } from '../motion/scheduler.js';

export function useMotionTimeline(events, missionId, paused) {
  const scheduler = useRef(null);
  if (!scheduler.current) scheduler.current = createMotionScheduler();
  const driver = useRef(null);
  const [snapshot, setSnapshot] = useState(EMPTY_MOTION);
  useEffect(() => {
    driver.current = createMotionDriver(scheduler.current, setSnapshot);
    return () => { driver.current.dispose(); driver.current = null; };
  }, []);
  useEffect(() => { driver.current.sync(events, missionId, paused); }, [events, missionId, paused]);
  return snapshot.missionId === missionId ? snapshot : EMPTY_MOTION;
}
