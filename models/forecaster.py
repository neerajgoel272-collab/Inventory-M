"""
AI Sales Forecasting Model
Uses an ensemble of Linear Regression + Moving Average with trend detection.
Falls back gracefully when data is sparse.

Techniques used:
  1. Feature engineering (day-of-week, week-of-year, lag features, rolling mean)
  2. Linear Regression (scikit-learn) as the primary model
  3. Exponential smoothing as fallback
  4. Confidence interval estimation via residual std
"""

import numpy as np
import pandas as pd
from datetime import date, timedelta
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error
import warnings
warnings.filterwarnings('ignore')


class SalesForecaster:
    """
    AI-powered sales forecaster for a single product time series.
    
    Usage:
        forecaster = SalesForecaster()
        result = forecaster.forecast(history_dict, forecast_days=30)
    """

    def __init__(self):
        self.model   = None
        self.scaler  = StandardScaler()
        self.model_name = 'LinearRegression'

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    def forecast(self, history: dict, forecast_days: int = 30) -> dict:
        """
        Generate a sales forecast.

        Parameters
        ----------
        history      : dict mapping 'YYYY-MM-DD' -> quantity_sold
        forecast_days: number of days to predict ahead

        Returns
        -------
        dict with keys: forecast, historical, model_used, accuracy_metrics
        """
        try:
            df = self._prepare_series(history)

            if len(df) < 7:
                return {'error': 'Need at least 7 days of sales data.'}

            # Choose model based on data size
            if len(df) >= 21:
                predictions, residual_std = self._fit_linear_regression(df, forecast_days)
                self.model_name = 'LinearRegression + FeatureEngineering'
            else:
                predictions, residual_std = self._exponential_smoothing(df, forecast_days)
                self.model_name = 'ExponentialSmoothing'

            # Build forecast list
            last_date = df['date'].max()
            forecast_list = []
            for i, pred in enumerate(predictions, 1):
                fc_date = last_date + timedelta(days=i)
                pred_val = max(0.0, round(float(pred), 2))
                forecast_list.append({
                    'date': fc_date.isoformat(),
                    'predicted_qty': pred_val,
                    'lower': max(0.0, round(pred_val - 1.96 * residual_std, 2)),
                    'upper': round(pred_val + 1.96 * residual_std, 2),
                })

            # Historical for chart overlay
            historical = [
                {'date': row['date'].isoformat(), 'qty': row['qty']}
                for _, row in df.iterrows()
            ]

            # Simple accuracy estimate on training data
            mae = self._compute_mae(df)

            return {
                'forecast': forecast_list,
                'historical': historical[-60:],   # last 60 days for chart
                'model_used': self.model_name,
                'accuracy_metrics': {
                    'mae': round(mae, 2),
                    'data_points': len(df),
                    'forecast_horizon': forecast_days,
                },
            }

        except Exception as e:
            return {'error': f'Forecasting failed: {str(e)}'}

    # ──────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _prepare_series(self, history: dict) -> pd.DataFrame:
        """Convert history dict to a complete daily DataFrame (filling gaps with 0)."""
        records = [{'date': pd.to_datetime(k), 'qty': float(v)} for k, v in history.items()]
        df = pd.DataFrame(records).sort_values('date').reset_index(drop=True)

        # Fill missing dates with 0
        date_range = pd.date_range(df['date'].min(), df['date'].max(), freq='D')
        df = df.set_index('date').reindex(date_range, fill_value=0).reset_index()
        df.columns = ['date', 'qty']
        return df

    def _engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create calendar + lag features for ML model."""
        df = df.copy()
        df['day_of_week']  = df['date'].dt.dayofweek          # 0=Mon
        df['day_of_month'] = df['date'].dt.day
        df['week_of_year'] = df['date'].dt.isocalendar().week.astype(int)
        df['month']        = df['date'].dt.month
        df['t']            = (df['date'] - df['date'].min()).dt.days  # time index

        # Lag features
        df['lag_1']  = df['qty'].shift(1).fillna(0)
        df['lag_7']  = df['qty'].shift(7).fillna(0)
        df['lag_14'] = df['qty'].shift(14).fillna(0)

        # Rolling statistics
        df['rolling_7_mean']  = df['qty'].rolling(7,  min_periods=1).mean()
        df['rolling_14_mean'] = df['qty'].rolling(14, min_periods=1).mean()
        df['rolling_7_std']   = df['qty'].rolling(7,  min_periods=1).std().fillna(0)

        return df

    def _fit_linear_regression(self, df: pd.DataFrame, forecast_days: int):
        """Train Linear Regression on engineered features and forecast."""
        df_feat = self._engineer_features(df)

        feature_cols = [
            't', 'day_of_week', 'day_of_month', 'week_of_year', 'month',
            'lag_1', 'lag_7', 'lag_14', 'rolling_7_mean', 'rolling_14_mean',
        ]

        # Drop rows with NaN lags (first 14 rows)
        train_df = df_feat.dropna(subset=feature_cols)
        X_train  = train_df[feature_cols].values
        y_train  = train_df['qty'].values

        X_scaled = self.scaler.fit_transform(X_train)

        self.model = LinearRegression()
        self.model.fit(X_scaled, y_train)

        # Residuals on training data
        y_pred       = self.model.predict(X_scaled)
        residuals    = y_train - y_pred
        residual_std = float(np.std(residuals))

        # ── Generate future features ──────────────────────────────────────────
        last_date    = df['date'].max()
        last_t       = int((last_date - df['date'].min()).days)
        last_vals    = list(df['qty'].values)

        predictions = []
        for i in range(1, forecast_days + 1):
            fc_date  = last_date + timedelta(days=i)
            t_val    = last_t + i
            dow      = fc_date.dayofweek
            dom      = fc_date.day
            woy      = int(fc_date.isocalendar()[1])
            mon      = fc_date.month

            lag_1    = last_vals[-1]  if len(last_vals) >= 1  else 0
            lag_7    = last_vals[-7]  if len(last_vals) >= 7  else 0
            lag_14   = last_vals[-14] if len(last_vals) >= 14 else 0
            roll_7   = float(np.mean(last_vals[-7:]))
            roll_14  = float(np.mean(last_vals[-14:]))

            feat     = np.array([[t_val, dow, dom, woy, mon, lag_1, lag_7, lag_14, roll_7, roll_14]])
            feat_sc  = self.scaler.transform(feat)
            pred     = float(self.model.predict(feat_sc)[0])
            pred     = max(0.0, pred)

            predictions.append(pred)
            last_vals.append(pred)

        return predictions, residual_std

    def _exponential_smoothing(self, df: pd.DataFrame, forecast_days: int):
        """Simple exponential smoothing fallback for short series."""
        alpha = 0.3
        values = df['qty'].values
        smoothed = [values[0]]
        for v in values[1:]:
            smoothed.append(alpha * v + (1 - alpha) * smoothed[-1])

        last_smooth = smoothed[-1]

        # Slight trend from last 7 days
        if len(values) >= 7:
            trend = (np.mean(values[-3:]) - np.mean(values[-7:-4])) / 4
        else:
            trend = 0.0

        predictions = [max(0.0, last_smooth + trend * i) for i in range(1, forecast_days + 1)]
        residual_std = float(np.std(np.array(values) - np.array(smoothed)))

        return predictions, max(residual_std, 0.5)

    def _compute_mae(self, df: pd.DataFrame) -> float:
        """Compute MAE on a simple 7-day rolling mean baseline."""
        if len(df) < 8:
            return 0.0
        actual = df['qty'].values[7:]
        pred   = df['qty'].rolling(7).mean().values[7:]
        valid  = ~np.isnan(pred)
        if not valid.any():
            return 0.0
        return float(mean_absolute_error(actual[valid], pred[valid]))
