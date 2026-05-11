import { useEffect, useCallback, useRef } from 'react';
import axios from 'axios';

export const useProactiveTracking = (sessionId: string, enabled: boolean = true) => {
  const idleTimer = useRef<NodeJS.Timeout>();
  const backCount = useRef(0);
  const lastPage = useRef(window.location.pathname);

  const reportEvent = useCallback(async (page: string, idle: number, backs: number, error?: string) => {
    if (!enabled) return;
    try {
      await axios.post('/api/events', {
        session_id: sessionId,
        page,
        idle_sec: idle,
        back_count: backs,
        form_error: error
      }, { timeout: 2000 });
    } catch (e) {
      console.warn('Proactive tracking failed:', e);
    }
  }, [sessionId, enabled]);

  useEffect(() => {
    if (!enabled) return;

    const handleVisibility = () => {
      if (document.hidden) {
        if (idleTimer.current) clearInterval(idleTimer.current);
      } else {
        idleTimer.current = setInterval(() => {
          reportEvent(window.location.pathname, Date.now(), backCount.current);
        }, 30000);
      }
    };

    const handlePopState = () => {
      backCount.current++;
      reportEvent(window.location.pathname, 0, backCount.current);
      lastPage.current = window.location.pathname;
    };

    const handleFormError = (e: Event) => {
      const target = e.target as HTMLFormElement;
      if (target?.querySelector?.(':invalid')) {
        reportEvent(window.location.pathname, 0, 0, 'form_validation_error');
      }
    };

    document.addEventListener('visibilitychange', handleVisibility);
    window.addEventListener('popstate', handlePopState);
    window.addEventListener('submit', handleFormError, true);
    
    idleTimer.current = setInterval(() => {
      reportEvent(window.location.pathname, Date.now(), backCount.current);
    }, 30000);

    return () => {
      if (idleTimer.current) clearInterval(idleTimer.current);
      document.removeEventListener('visibilitychange', handleVisibility);
      window.removeEventListener('popstate', handlePopState);
      window.removeEventListener('submit', handleFormError, true);
    };
  }, [reportEvent]);

  return { backCount: backCount.current };
};