import React, { createContext, useState, useContext, useEffect, useCallback } from 'react';
import apiClient, { setUnauthorizedHandler } from '../api/axiosConfig';

const UserContext = createContext();

export const useUser = () => useContext(UserContext);

export const UserProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  // Network/5xx failure from the last /user/ refresh. Kept separate from the
  // logged-out state (user === null) so a blip doesn't bounce a valid session.
  const [userError, setUserError] = useState('');

  const fetchUser = useCallback(async () => {
    try {
      const response = await apiClient.get('/user/');
      setUser(response.data);
      setUserError('');
    } catch (error) {
      if (error.response && (error.response.status === 403 || error.response.status === 401)) {
        setUser(null);
        setUserError('');
      } else {
        console.error("An unexpected error occurred fetching user data:", error);
        setUserError('Could not refresh your session. Check your connection.');
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  // Let the axios interceptor drop the stale user when any request mid-session
  // comes back 401 (it redirects to /login right after). 403s are permission
  // denials, not session expiry, and stay with the calling component.
  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null));
    return () => setUnauthorizedHandler(null);
  }, []);

  const loginUser = async (username, password) => {
    try {
      const response = await apiClient.post('/login/', { username, password });
      setUser(response.data);
      return { success: true };
    } catch (error) {
      console.error("Login failed:", error.response?.data);
      setUser(null);
      return { success: false, message: error.response?.data?.detail || "Login failed." };
    }
  };

  const logoutUser = async () => {
    try {
      await apiClient.post('/logout/');
    } catch (error) {
      console.error("Logout failed:", error);
    } finally {
      setUser(null);
    }
  };

  const refreshUser = useCallback(() => {
    return fetchUser();
  }, [fetchUser]);

  const value = { user, isLoading, userError, loginUser, logoutUser, refreshUser };

  return (
    <UserContext.Provider value={value}>
      {!isLoading && children}
    </UserContext.Provider>
  );
};
