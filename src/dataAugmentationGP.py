import GPy
import numpy as np
import matplotlib.pyplot as plt

from src.abstractGP import AbstractGP
from src.augmentationIterators import augmentIter
from sklearn.metrics import mean_squared_error
from time import sleep


class DataAugmentationGP(AbstractGP):

    def __init__(self, tau: float, n: int, input_dim: int, f_high: callable, adapt_steps: int = 0, f_low: callable = None, lf_X: np.ndarray = None, lf_Y: np.ndarray = None, lf_hf_adapt_ratio: int = 1,):
        '''
        input: tau
            distance to neighbour points used in taylor expansion
        input n: 
            number of derivatives which will be included when training the high-fidelity model,
            adds 2*n+1 dimensions to the high-fidelity training data
        input input_dim:
            dimensionality of the input data
        input f_low:
            closed form of a low-fidelity prediction function, 
            if not provided, call self.lf_fit() to train a low-fidelity GP which will be used for low-fidelity predictions instead
        '''
        self.tau = tau
        self.n = n
        self.input_dim = input_dim
        self.__f_high_real = f_high
        self.f_low = f_low
        self.adapt_steps = adapt_steps
        self.lf_hf_adapt_ratio = lf_hf_adapt_ratio
        self.a = self.b = None

        lf_model_params_are_valid = (f_low is not None) ^ (
            (lf_X is not None) and (lf_Y is not None) and (lf_hf_adapt_ratio is not None))
        assert lf_model_params_are_valid, 'define low-fidelity model either by mean function or by Data'

        self.data_driven_lf_approach = f_low is None

        if self.data_driven_lf_approach:
            self.__update_input_borders(lf_X)
            self.lf_X = lf_X
            self.lf_Y = lf_Y

            self.lf_model = GPy.models.GPRegression(
                X=lf_X, Y=lf_Y, initialize=True
            )
            self.lf_model.optimize()
            self.__adapt_lf()
            self.__lf_mean_predict = lambda t: self.lf_model.predict(t)[0]
        else:
            self.__lf_mean_predict = f_low

    def fit(self, hf_X):
        self.__update_input_borders(hf_X)
        self.hf_X = hf_X.reshape(-1, 1)
        # high fidelity data is as precise as ground truth data
        self.hf_Y = self.__f_high_real(self.hf_X)
        # augment input data before prediction
        augmented_hf_X = self.__augment_Data(self.hf_X)

        self.hf_model = GPy.models.GPRegression(
            X=augmented_hf_X,
            Y=self.hf_Y,
            kernel=self.NARGP_kernel(),
            initialize=True
        )
        self.hf_model.optimize_restarts(num_restarts=6, verbose=False)  # ARD

    def adapt(self, plot=False, X_test=None, Y_test=None, verbose=False):
        if plot:
            # prepare subplotting
            subplots_per_row = int(np.ceil(np.sqrt(self.adapt_steps)))
            subplots_per_column = int(np.ceil(self.adapt_steps / subplots_per_row))
            fig, axs = plt.subplots(
                subplots_per_row, 
                subplots_per_column,
                sharey='row',
                sharex=True,
                figsize=(20, 10))
            fig.suptitle(
                'Uncertainty development during the adaptation process')
            X = np.linspace(self.a, self.b, 200).reshape(-1, 1)
            log_mses = []

        for i in range(self.adapt_steps):
            acquired_x = self.get_input_with_highest_uncertainty()
            if verbose:
                print('new x acquired: {}'.format(acquired_x))
            if plot:
                # add subplott in 
                _, uncertainties = self.predict(X)
                ax = axs.flatten()[i]
                ax.axes.xaxis.set_visible(False)
                log_mse = self.assess_log_mse(X_test, Y_test)
                log_mses.append(log_mse)
                ax.set_title('log mse: {}'.format(np.round(log_mse, 4)))
                ax.plot(X, uncertainties)
                ax.plot(acquired_x.reshape(-1, 1), 0, 'rx')

            self.fit(np.append(self.hf_X, acquired_x))
            # self.fit(self.hf_X)
        if plot:
            plt2 = plt.figure(2)
            plt.title('logarithmic mean square error')
            plt.xlabel('adapt step')
            plt.ylabel('log mse')
            plt.plot(np.arange(self.adapt_steps), np.array(log_mses))

    def get_input_with_highest_uncertainty(self, precision: int = 200):
        X = np.linspace(self.a, self.b, precision).reshape(-1, 1)
        _, uncertainties = self.predict(X)
        # plt.plot(X, uncertainties)
        # plt.show()
        index_with_highest_uncertainty = np.argmax(uncertainties)
        return X[index_with_highest_uncertainty]

    def __adapt_lf(self):
        X = np.linspace(self.a, self.b, 100).reshape(-1, 1)
        for i in range(self.adapt_steps * self.lf_hf_adapt_ratio):
            uncertainties = self.lf_model.predict(X)[1]
            maxIndex = np.argmax(uncertainties)
            new_x = X[maxIndex].reshape(-1, 1)
            new_y = self.lf_model.predict(new_x)[0]

            self.lf_X = np.append(self.lf_X, new_x, axis=0)
            self.lf_Y = np.append(self.lf_Y, new_y, axis=0)

            self.lf_model = GPy.models.GPRegression(
                self.lf_X, self.lf_Y, initialize=True
            )
            self.lf_model.optimize_restarts(
                num_restarts=5,
                optimizer='tnc'
            )

    def predict(self, X_test):
        assert X_test.ndim == 2
        assert X_test.shape[1] == self.input_dim
        X_test = self.__augment_Data(X_test)
        return self.hf_model.predict(X_test)

    def predict_means(self, X_test):
        means, _ = self.predict(X_test)
        return means

    def predict_variance(self, X_test):
        _, uncertainties = self.predict(X_test)
        return uncertainties

    def plot(self):
        assert self.input_dim == 1, '2d plots need one-dimensional data'
        self.__plot()

    def plot_forecast(self, forecast_range=.5):
        self.__plot(exceed_range_by=forecast_range)

    def assess_log_mse(self, X_test, y_test):
        predictions = self.predict_means(X_test)
        mse = mean_squared_error(y_true=y_test, y_pred=predictions)
        log_mse = np.log2(mse)
        return log_mse

    def NARGP_kernel(self, kern_class1=GPy.kern.RBF, kern_class2=GPy.kern.RBF, kern_class3=GPy.kern.RBF):
        std_input_dim = self.input_dim
        std_indezes = np.arange(self.input_dim)

        aug_input_dim = 2 * self.n + 1
        aug_indezes = np.arange(self.input_dim, self.input_dim + aug_input_dim)

        kern1 = kern_class1(aug_input_dim, active_dims=aug_indezes)
        kern2 = kern_class2(std_input_dim, active_dims=std_indezes)
        kern3 = kern_class3(std_input_dim, active_dims=std_indezes)
        return kern1 * kern2 + kern3

    def __plot(self, confidence_inteval_width=2, plot_lf=True, plot_hf=True, plot_pred=True, exceed_range_by=0):
        point_density = 500
        X = np.linspace(self.a, self.b * (1 + exceed_range_by),
                        int(point_density * (1 + exceed_range_by))).reshape(-1, 1)
        pred_mean, pred_variance = self.predict(X.reshape(-1, 1))
        pred_mean = pred_mean.flatten()
        pred_variance = pred_variance.flatten()

        if (not self.data_driven_lf_approach):
            self.lf_X = np.linspace(self.a, self.b, 50).reshape(-1, 1)
            self.lf_Y = self.__lf_mean_predict(self.lf_X)

        lf_color, hf_color, pred_color = 'r', 'b', 'g'

        if plot_lf:
            # plot low fidelity
            plt.plot(self.lf_X, self.lf_Y, lf_color +
                     'x', label='low-fidelity')
            plt.plot(X, self.__lf_mean_predict(X), lf_color,
                     label='f_low', linestyle='dashed')

        if plot_hf:
            # plot high fidelity
            plt.plot(self.hf_X, self.hf_Y, hf_color +
                     'x', label='high-fidelity')
            plt.plot(X, self.__f_high_real(X), hf_color,
                     label='f_high', linestyle='dashed')

        if plot_pred:
            # plot prediction
            plt.plot(X, pred_mean, pred_color, label='prediction')
            plt.fill_between(X.flatten(),
                             y1=pred_mean - confidence_inteval_width * pred_variance,
                             y2=pred_mean + confidence_inteval_width * pred_variance,
                             color=(0, 1, 0, .75)
                             )

        plt.legend()

    def __augment_Data(self, X):
        assert isinstance(X, np.ndarray), 'input must be an array'
        assert len(X) > 0, 'input must be non-empty'
        new_entries = np.concatenate([
            self.__lf_mean_predict(X + i * self.tau) for i in augmentIter(self.n)
        ], axis=1)
        return np.concatenate([X, new_entries], axis=1)

    def __update_input_borders(self, X: np.ndarray):
        if self.a == None and self.b == None:
            self.a = np.min(X)
            self.b = np.max(X)
        else:
            if np.min(X) < self.a:
                self.a = np.min(X)
            if self.b < np.max(X):
                self.b = np.max(X)

#   GP_augmented_data, select better kernel than RBF
#   NARGP
#   MFDGP

# complete adapt (just for high) (look in GPY, bayesian optimization toolbox)
# complete adapt (for low)
# combine both
# check results
# describe the process
