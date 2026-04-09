import { createContext, useState, useEffect } from "react";
import axios from "axios";

// In production (Vercel), we use relative paths so Vercel Rewrites can handle the proxy.
// This avoids "Mixed Content" (HTTPS -> HTTP) issues.
const API_URL = import.meta.env.VITE_API_URL || (import.meta.env.PROD ? "" : "http://localhost:8000");
axios.defaults.baseURL = API_URL;

export const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [token, setToken] = useState(localStorage.getItem("codemind_token"));
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // Configure Axios globally to attach the token if it exists
  useEffect(() => {
    if (token) {
      axios.defaults.headers.common["Authorization"] = `Bearer ${token}`;
      localStorage.setItem("codemind_token", token);
      fetchUser();
    } else {
      delete axios.defaults.headers.common["Authorization"];
      localStorage.removeItem("codemind_token");
      setUser(null);
      setLoading(false);
    }
  }, [token]);

  const fetchUser = async () => {
    try {
      const res = await axios.get("/api/auth/me");
      setUser(res.data);
    } catch (err) {
      console.error("Failed to fetch user", err);
      logout();
    } finally {
      setLoading(false);
    }
  };

  const login = async (username, password) => {
    const res = await axios.post("/api/auth/login", { username, password });
    setToken(res.data.access_token);
    return res.data;
  };

  const register = async (username, email, password) => {
    const res = await axios.post("/api/auth/register", { username, email, password });
    setToken(res.data.access_token);
    return res.data;
  };

  const logout = () => {
    setToken(null);
  };

  return (
    <AuthContext.Provider value={{ token, user, login, register, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
};
