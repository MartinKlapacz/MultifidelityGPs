from src.MFDataFusion import MultifidelityDataFusion
import threading
import matplotlib.pyplot as plt
import numpy as np


class MethodAssessment:
    def __init__(self, models, X_test, Y_test, title=""):
        assert type(models) is list
        assert len(models) > 0
        assert np.all([models[0].input_dim == m.input_dim for m in models]), \
            "all models must have same input dim"
        assert len(set(map(lambda m: m.name, models))) == len(models), \
            "models must have different names"
        self.models = models
        self.X_test = X_test
        self.Y_test = Y_test
        self.title = title

    def fit_models(self, X_train):
        """train all models in self.models

        :param X_train: high-fidelity training vectors used to train the models
        :type X_train: [type]
        """
        for model in self.models:
            model.fit(hf_X=X_train)

    def adapt_models(self, adapt_steps: int, plot_mode: str = None, eps: float = 0):
        """adapt all models in self.models

        :param adapt_steps: number of new hf-points per model
        :type adapt_steps: int
        :param plot_mode: no plot or mse plot, defaults to None
        :type plot_mode: str, optional
        :param eps: if (during adaptation) max. uncertainty becomes smaller than 
        eps, interupt process, defauts to 0 because we usually don't want to interrupt 
        the model when comparing it with other models
        :type eps: float
        """
        assert plot_mode in [None, 'e']
        if plot_mode == 'e':
            eps = 0
        for model in self.models:
            model.adapt(adapt_steps, plot_mode=plot_mode,
                        X_test=self.X_test,
                        Y_test=self.Y_test,
                        eps=eps)
        plt.title(self.title)

    def plot(self):
        for model in self.models:
            model.plot()

    def plot_forecast(self, forecast_range):
        for model in self.models:
            model.plot_forecast(forecast_range)

    def mses(self):
        """compute the models' mean square errors

        :return: dictionary of all mses
        :rtype: dict
        """
        mses = {}
        for model in self.models:
            mses[model.name] = model.get_mse(self.X_test, self.Y_test)
        return mses

    def plot_compare_with_exact(self):
        plt.figure()
        for model in self.models:
            model.plot_compare_with_exact()
