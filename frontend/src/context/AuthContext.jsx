import React, { createContext, useContext, useState, useEffect } from 'react';
import { authApi } from '../api/apiClient';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(() => {
    try {
      const stored = localStorage.getItem('user');
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  });

  const [theme, setThemeState] = useState(() => {
    return localStorage.getItem('theme') || 'light';
  });

  const [language, setLanguageState] = useState(() => {
    return localStorage.getItem('language') || 'en';
  });

  // Apply theme class to document root element
  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
      root.setAttribute('data-theme', 'dark');
    } else {
      root.classList.remove('dark');
      root.setAttribute('data-theme', 'light');
    }
    localStorage.setItem('theme', theme);
  }, [theme]);

  useEffect(() => {
    localStorage.setItem('language', language);
  }, [language]);

  const login = async (employeeId, password) => {
    const data = await authApi.login(employeeId, password);
    const currentUser = authApi.getCurrentUser();
    setUser(currentUser);
    return data;
  };

  const logout = () => {
    authApi.logout();
    setUser(null);
  };

  const updateUser = async (profileData) => {
    const updated = await authApi.updateProfile(profileData);
    setUser(updated);
    return updated;
  };

  const setTheme = (newTheme) => {
    setThemeState(newTheme);
  };

  const setLanguage = (newLang) => {
    setLanguageState(newLang);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        setUser,
        theme,
        setTheme,
        language,
        setLanguage,
        login,
        logout,
        updateUser,
        isAuthenticated: !!user && !!localStorage.getItem('accessToken'),
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export default AuthContext;
