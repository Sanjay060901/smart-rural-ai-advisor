// src/services/cognitoAuth.js
// Cognito authentication — sign-up with phone+PIN, sign-in, token management

import {
    CognitoUserPool,
    CognitoUser,
    AuthenticationDetails,
    CognitoUserAttribute,
} from 'amazon-cognito-identity-js';

import config from '../config';

const POOL_DATA = {
    UserPoolId: config.COGNITO_USER_POOL_ID,
    ClientId: config.COGNITO_CLIENT_ID,
};

const userPool = new CognitoUserPool(POOL_DATA);

/**
 * Format phone to Cognito format: +91XXXXXXXXXX
 */
function formatPhone(phone) {
    const digits = phone.replace(/\D/g, '').slice(-10);
    return `${config.COUNTRY_CODE}${digits}`;
}

/**
 * Sign up a new user with phone number and PIN.
 * Cognito auto-confirms via Pre-SignUp trigger.
 * @param {string} phone - 10-digit phone
 * @param {string} pin   - 6+ char PIN/password
 * @param {string} name  - Farmer name
 * @param {string} [email] - Optional email for PIN recovery
 * @returns {Promise<{ userSub: string, codeDeliveryDetails: object }>}
 */
export function signUp(phone, pin, name, email) {
    return new Promise((resolve, reject) => {
        const cognitoPhone = formatPhone(phone);
        const attributes = [
            new CognitoUserAttribute({ Name: 'phone_number', Value: cognitoPhone }),
            new CognitoUserAttribute({ Name: 'name', Value: name }),
        ];
        if (email && email.trim()) {
            attributes.push(new CognitoUserAttribute({ Name: 'email', Value: email.trim() }));
        }

        userPool.signUp(cognitoPhone, pin, attributes, null, (err, result) => {
            if (err) return reject(err);
            resolve({
                userSub: result.userSub,
                codeDeliveryDetails: result.codeDeliveryDetails,
            });
        });
    });
}

/**
 * Confirm sign-up with the OTP code sent via SMS.
 * @param {string} phone - 10-digit phone
 * @param {string} code  - 6-digit OTP
 * @returns {Promise<string>} 'SUCCESS'
 */
export function confirmSignUp(phone, code) {
    return new Promise((resolve, reject) => {
        const cognitoPhone = formatPhone(phone);
        const cognitoUser = new CognitoUser({
            Username: cognitoPhone,
            Pool: userPool,
        });

        cognitoUser.confirmRegistration(code, true, (err, result) => {
            if (err) return reject(err);
            resolve(result); // 'SUCCESS'
        });
    });
}

/**
 * Resend the sign-up confirmation code.
 * @param {string} phone - 10-digit phone
 * @returns {Promise<object>} code delivery details
 */
export function resendConfirmationCode(phone) {
    return new Promise((resolve, reject) => {
        const cognitoPhone = formatPhone(phone);
        const cognitoUser = new CognitoUser({
            Username: cognitoPhone,
            Pool: userPool,
        });

        cognitoUser.resendConfirmationCode((err, result) => {
            if (err) return reject(err);
            resolve(result);
        });
    });
}

/**
 * Sign in with phone + PIN. Returns a session with JWT tokens.
 * @param {string} phone - 10-digit phone
 * @param {string} pin   - PIN/password
 * @returns {Promise<{ idToken: string, accessToken: string, refreshToken: string }>}
 */
export function signIn(phone, pin) {
    return new Promise((resolve, reject) => {
        const cognitoPhone = formatPhone(phone);
        const cognitoUser = new CognitoUser({
            Username: cognitoPhone,
            Pool: userPool,
        });

        const authDetails = new AuthenticationDetails({
            Username: cognitoPhone,
            Password: pin,
        });

        cognitoUser.authenticateUser(authDetails, {
            onSuccess: (session) => {
                resolve({
                    idToken: session.getIdToken().getJwtToken(),
                    accessToken: session.getAccessToken().getJwtToken(),
                    refreshToken: session.getRefreshToken().getToken(),
                });
            },
            onFailure: (err) => reject(err),
        });
    });
}

/**
 * Get the current authenticated user's session (auto-refreshes if needed).
 * Returns null if no user is signed in.
 * @returns {Promise<{ idToken: string, accessToken: string, phone: string, name: string } | null>}
 */
export function getSession() {
    return new Promise((resolve) => {
        const user = userPool.getCurrentUser();
        if (!user) return resolve(null);

        user.getSession((err, session) => {
            if (err || !session || !session.isValid()) return resolve(null);

            // Try to get user attributes but don't let it block
            // (getUserAttributes makes a network call that can hang)
            const fallbackTimer = setTimeout(() => {
                resolve({
                    idToken: session.getIdToken().getJwtToken(),
                    accessToken: session.getAccessToken().getJwtToken(),
                    phone: '',
                    name: '',
                });
            }, 2000);

            user.getUserAttributes((attrErr, attrs) => {
                clearTimeout(fallbackTimer);
                let phone = '';
                let name = '';
                if (!attrErr && attrs) {
                    for (const a of attrs) {
                        if (a.Name === 'phone_number') phone = a.Value;
                        if (a.Name === 'name') name = a.Value;
                    }
                }
                resolve({
                    idToken: session.getIdToken().getJwtToken(),
                    accessToken: session.getAccessToken().getJwtToken(),
                    phone,
                    name,
                });
            });
        });
    });
}

/**
 * Get only the current ID token (for API calls).
 * Returns null if not authenticated.
 * @returns {Promise<string | null>}
 */
export function getIdToken() {
    return new Promise((resolve) => {
        const user = userPool.getCurrentUser();
        if (!user) return resolve(null);

        user.getSession((err, session) => {
            if (err || !session || !session.isValid()) return resolve(null);
            resolve(session.getIdToken().getJwtToken());
        });
    });
}

/**
 * Sign out the current user (clears local session).
 */
export function signOut() {
    const user = userPool.getCurrentUser();
    if (user) user.signOut();
}

/**
 * Initiate forgot-password flow — sends an OTP to the user's phone via SMS.
 * @param {string} phone - 10-digit phone
 * @returns {Promise<object>} code delivery details
 */
export function forgotPassword(phone) {
    return new Promise((resolve, reject) => {
        const cognitoPhone = formatPhone(phone);
        const cognitoUser = new CognitoUser({
            Username: cognitoPhone,
            Pool: userPool,
        });

        cognitoUser.forgotPassword({
            onSuccess: (data) => resolve(data),
            onFailure: (err) => reject(err),
            inputVerificationCode: (data) => resolve(data),
        });
    });
}

/**
 * Confirm forgot-password flow — set new PIN using the OTP code.
 * @param {string} phone - 10-digit phone
 * @param {string} code  - OTP received via SMS
 * @param {string} newPin - New PIN/password (6+ chars)
 * @returns {Promise<string>} 'SUCCESS'
 */
export function confirmForgotPassword(phone, code, newPin) {
    return new Promise((resolve, reject) => {
        const cognitoPhone = formatPhone(phone);
        const cognitoUser = new CognitoUser({
            Username: cognitoPhone,
            Pool: userPool,
        });

        cognitoUser.confirmPassword(code, newPin, {
            onSuccess: () => resolve('SUCCESS'),
            onFailure: (err) => reject(err),
        });
    });
}

/**
 * Change the current user's password (PIN).
 * Requires the user to be authenticated.
 * @param {string} oldPin - Current PIN/password
 * @param {string} newPin - New PIN/password (6+ chars)
 * @returns {Promise<string>} 'SUCCESS'
 */
export function changePassword(oldPin, newPin) {
    return new Promise((resolve, reject) => {
        const user = userPool.getCurrentUser();
        if (!user) return reject(new Error('No authenticated user'));

        user.getSession((err, session) => {
            if (err || !session || !session.isValid()) {
                return reject(new Error('No valid session'));
            }
            user.changePassword(oldPin, newPin, (changeErr, result) => {
                if (changeErr) return reject(changeErr);
                resolve(result); // 'SUCCESS'
            });
        });
    });
}

/**
 * Update the current user's email attribute.
 * @param {string} email - New email address
 * @returns {Promise<string>} 'SUCCESS'
 */
export function updateEmail(email) {
    return new Promise((resolve, reject) => {
        const user = userPool.getCurrentUser();
        if (!user) return reject(new Error('No authenticated user'));

        user.getSession((err, session) => {
            if (err || !session || !session.isValid()) {
                return reject(new Error('No valid session'));
            }
            const attrs = [
                new CognitoUserAttribute({ Name: 'email', Value: email.trim() }),
            ];
            user.updateAttributes(attrs, (updateErr, result) => {
                if (updateErr) return reject(updateErr);
                resolve(result);
            });
        });
    });
}

/**
 * Send a verification code to the user's email.
 * Email must be set but NOT yet verified.
 * @returns {Promise<object>} code delivery details
 */
export function sendEmailVerificationCode() {
    return new Promise((resolve, reject) => {
        const user = userPool.getCurrentUser();
        if (!user) return reject(new Error('No authenticated user'));

        user.getSession((err, session) => {
            if (err || !session || !session.isValid()) {
                return reject(new Error('No valid session'));
            }
            user.getAttributeVerificationCode('email', {
                onSuccess: () => resolve({ sent: true }),
                onFailure: (verifyErr) => reject(verifyErr),
                inputVerificationCode: (data) => resolve(data),
            });
        });
    });
}

/**
 * Verify the user's email with the code received.
 * @param {string} code - 6-digit verification code
 * @returns {Promise<string>} 'SUCCESS'
 */
export function verifyEmail(code) {
    return new Promise((resolve, reject) => {
        const user = userPool.getCurrentUser();
        if (!user) return reject(new Error('No authenticated user'));

        user.getSession((err, session) => {
            if (err || !session || !session.isValid()) {
                return reject(new Error('No valid session'));
            }
            user.verifyAttribute('email', code, {
                onSuccess: (result) => resolve(result),
                onFailure: (verifyErr) => reject(verifyErr),
            });
        });
    });
}

/**
 * Check if the current user's email is verified.
 * @returns {Promise<boolean>}
 */
export function isEmailVerified() {
    return new Promise((resolve) => {
        const user = userPool.getCurrentUser();
        if (!user) return resolve(false);

        user.getSession((err, session) => {
            if (err || !session || !session.isValid()) return resolve(false);
            user.getUserAttributes((attrErr, attrs) => {
                if (attrErr || !attrs) return resolve(false);
                const emailVerified = attrs.find(a => a.Name === 'email_verified');
                resolve(emailVerified?.Value === 'true');
            });
        });
    });
}

/**
 * Delete the currently authenticated user from Cognito.
 * Requires an active session.
 * @returns {Promise<string>} 'SUCCESS'
 */
export function deleteUser() {
    return new Promise((resolve, reject) => {
        const user = userPool.getCurrentUser();
        if (!user) return reject(new Error('No authenticated user'));

        user.getSession((err, session) => {
            if (err || !session || !session.isValid()) {
                return reject(new Error('No valid session'));
            }
            user.deleteUser((deleteErr, result) => {
                if (deleteErr) return reject(deleteErr);
                resolve(result || 'SUCCESS');
            });
        });
    });
}

/**
 * Check if a user exists in the pool by attempting authentication
 * with a dummy password. This avoids the forgotPassword() side-effect
 * of sending an actual SMS/email to the user.
 *
 * - UserNotFoundException     → user does NOT exist
 * - NotAuthorizedException    → user EXISTS (wrong password)
 * - UserNotConfirmedException → user EXISTS (not confirmed)
 * - Any other error           → assume exists (safe default)
 *
 * @param {string} phone - 10-digit phone
 * @returns {Promise<boolean>}
 */
export function userExists(phone) {
    return new Promise((resolve) => {
        const cognitoPhone = formatPhone(phone);
        const cognitoUser = new CognitoUser({
            Username: cognitoPhone,
            Pool: userPool,
        });

        const authDetails = new AuthenticationDetails({
            Username: cognitoPhone,
            Password: '__existence_check_dummy_pwd__',
        });

        cognitoUser.authenticateUser(authDetails, {
            onSuccess: () => resolve(true), // unlikely but user exists
            onFailure: (err) => {
                if (err.code === 'UserNotFoundException') return resolve(false);
                // NotAuthorizedException or UserNotConfirmedException → user exists
                resolve(true);
            },
        });
    });
}
