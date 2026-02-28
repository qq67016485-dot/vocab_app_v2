import React, { createContext, useState, useContext, useEffect, useCallback } from 'react';
import apiClient from '../api/axiosConfig';

const UserContext = createContext();

export const useUser = () => useContext(UserContext);

export const UserProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchUser = useCallback(async () => {
    try {
      const response = await apiClient.get('/user/');
      setUser(response.data);
    } catch (error) {
      if (error.response && (error.response.status === 403 || error.response.status === 401)) {
        setUser(null);
      } else {
        console.error("An unexpected error occurred fetching user data:", error);
        setUser(null);
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUser();
  }, [fetchUser]);

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

  const value = { user, isLoading, loginUser, logoutUser, refreshUser };

  return (
    <UserContext.Provider value={value}>
      {!isLoading && children}
    </UserContext.Provider>
  );
};
