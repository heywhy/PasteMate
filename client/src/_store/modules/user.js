import axios from 'axios'

export default {
  namespaced: true,

  state: {
    userID: null,
    username: null,
    email: null
  },

  actions: {
    signUp(context, payload) {
      return new Promise((resolve, reject) => {
        axios.post('/api/user/register', payload, {withCredentials: true})
          .then((response) => {
            context.commit('UPDATE_USER', [response.data.username, response.data.userID, response.data.email]);
            resolve(response);
          })
          .catch((error) => {
            context.commit('UPDATE_USER', [null, null]);
            reject(error);
          });
      })
    },

    signIn(context, payload) {
      return new Promise((resolve, reject) => {
        axios.post('/api/user/login', payload, {withCredentials: true})
          .then((response) => {
            context.commit('UPDATE_USER', [response.data.username, response.data.userID, response.data.email]);
            resolve(response);
          })
          .catch((error) => {
            context.commit('UPDATE_USER', [null, null]);
            reject(error);
          });
      })
    },

    signOut(context) {
      return new Promise((resolve, reject) => {
        axios.get('/api/auth/revoke', {withCredentials: true})
          .then((response) => {
            context.commit('UPDATE_USER', [null, null, null]);
            resolve(response);
          })
          .catch((error) => {
            reject(error);
          });
      })
    },

    // Get a new access token using their refresh token, and if it's valid, retrieve the current user with it.
    refreshUser(context) {
      return new Promise((resolve, reject) => {
        axios.get('/api/auth/refresh', {withCredentials: true})
          .then((response) => {
            context.dispatch('retrieveCurrentUser');
            resolve(response);
          })
          .catch((error) => {
            context.commit('UPDATE_USER', [null, null, null]);
            reject(error);
          });
      })
    },

    // Get their current user details using their access token.
    retrieveCurrentUser(context) {
      return new Promise((resolve, reject) => {
        axios.get('/api/auth/current_user', {withCredentials: true})
          .then((response) => {
            context.commit('UPDATE_USER', [response.data.username, response.data.userID, response.data.email]);
            resolve(response);
          })
          .catch((error) => {
            context.commit('UPDATE_USER', [null, null]);
            reject(error);
          });
      })
    }
  },

  mutations: {
    UPDATE_USER(state, payload) {
      [state.username, state.userID, state.email] = [...payload];
    }
  },

  getters: {
    username: state => {
      return state.username;
    },

    userID: state => {
      return state.userID;
    },

    email: state => {
      return state.email;
    }
  }
}
