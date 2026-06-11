/**
 * Type definitions for Authentication
 */

// User
export interface User {
  id: string;
  email: string;
  full_name?: string;
  created_at: string;
  is_active: boolean;
}

// Login Request
export interface LoginRequest {
  email: string;
  password: string;
}

// Register Request
export interface RegisterRequest {
  email: string;
  password: string;
  full_name?: string;
}

// Auth Response
export interface AuthResponse {
  token: string;
  user: User;
}

// Auth State
export interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
}

// Password Change Request
export interface PasswordChangeRequest {
  current_password: string;
  new_password: string;
  confirm_password: string;
}

// Profile Update Request
export interface ProfileUpdateRequest {
  full_name?: string;
  email?: string;
}
