import NextAuth from "next-auth";
import type { NextAuthOptions } from "next-auth";

export const authOptions: NextAuthOptions = {
  providers: [
    {
      id: "odoo",
      name: "Odoo",
      type: "oauth",
      version: "2.0",
      authorization: {
        url: process.env.ODOO_OAUTH_AUTHORIZE_URL || "https://odoo/restapi/1.0/common/oauth2/authorize",
        params: {
          client_id: process.env.ODOO_OAUTH_CLIENT_ID,
          redirect_uri: process.env.ODOO_OAUTH_REDIRECT_URI,
          response_type: "code",
        },
      },
      token: {
        url: process.env.ODOO_OAUTH_TOKEN_URL || "https://odoo/restapi/1.0/common/oauth2/access_token",
        params: {
          client_id: process.env.ODOO_OAUTH_CLIENT_ID,
          client_secret: process.env.ODOO_OAUTH_CLIENT_SECRET,
          redirect_uri: process.env.ODOO_OAUTH_REDIRECT_URI,
          grant_type: "authorization_code",
        },
      },
      userinfo: {
        url: process.env.ODOO_OAUTH_USERINFO_URL || "https://odoo/restapi/1.0/common/oauth2/userinfo",
      },
      profile(profile) {
        return {
          id: profile.id || profile.sub,
          name: profile.name || profile.login,
          email: profile.email,
        };
      },
      clientId: process.env.ODOO_OAUTH_CLIENT_ID,
      clientSecret: process.env.ODOO_OAUTH_CLIENT_SECRET,
    },
  ],
  session: {
    strategy: "jwt",
  },
  callbacks: {
    async jwt({ token, user, account }) {
      if (account) {
        token.accessToken = account.access_token;
      }
      if (user) {
        token.user = user;
      }
      return token;
    },
    async session({ session, token }) {
      session.accessToken = token.accessToken;
      session.user = token.user as any;
      return session;
    },
  },
  secret: process.env.NEXTAUTH_SECRET,
};

const handler = NextAuth(authOptions);
export { handler as GET, handler as POST };