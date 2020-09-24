from .apiwrapper import api_call
from .layout import *
from .utils.xcutils import *
from .xcdb.xcdb import *
from .domain import XcDomain


class XcDBChecker(XcDomain):
    suspend_info = None

    def __init__(self):
        super(XcDBChecker, self).__init__()

    def check_price_daily(self, code, start, end, astype, flag=IOFLAG.ERASE_INVALID):
        tstart = pd.Timestamp(start)
        tend = pd.Timestamp(end)
        vdates = gen_keys_monthly(tstart, tend, self.asset_lifetime(code, astype), self.trade_cal)
        if len(vdates) == 0:
            return

        db = self.facc(TusSdbs.SDB_DAILY_PRICE.value + code, EQUITY_DAILY_PRICE_META)

        if flag == IOFLAG.ERASE_ALL:
            for n, dd in enumerate(vdates):
                dtkey = dd.strftime(DATE_FORMAT)
                db.remove(dtkey)
        elif flag == IOFLAG.ERASE_INVALID:
            for n, dd in enumerate(vdates):
                dtkey = dd.strftime(DATE_FORMAT)
                val = db.load(dtkey, raw_mode=True)
                bvalid = integrity_check_km_vday(dd, val[:, 4], self.trade_cal,
                                                 self.stock_suspend(code))
                if not bvalid:
                    db.remove(dtkey)

        return

    def check_price_minute(self, code, start, end, freq='1min', astype=None, flag=IOFLAG.ERASE_INVALID):
        if freq not in XTUS_FREQS:
            return None

        tstart = pd.Timestamp(start)
        tend = pd.Timestamp(end)
        vdates = gen_keys_daily(tstart, tend, self.asset_lifetime(code, astype),
                                self.trade_cal)
        if len(vdates) == 0:
            return

        db = self.facc((TusSdbs.SDB_MINUTE_PRICE.value + code + freq),
                       EQUITY_MINUTE_PRICE_META)

        if flag == IOFLAG.ERASE_ALL:
            for n, dd in enumerate(vdates):
                dtkey = dd.strftime(DATE_FORMAT)
                db.remove(dtkey)
        else:
            for n, dd in enumerate(vdates):
                dtkey = dd.strftime(DATE_FORMAT)
                val = db.load(dtkey, raw_mode=True)
                if val is not None:
                    bvalid = integrity_check_kd_vmin(dd, val[:, 4], self.trade_cal,
                                                     self.stock_suspend(code), freq=freq, code=code)
                    if not bvalid:
                        db.remove(dtkey)
        return

    def check_stock_dayinfo(self, code, start, end, flag=IOFLAG.ERASE_INVALID):
        """

        :param code:
        :param start:
        :param end:
        :return:
        """
        tstart = pd.Timestamp(start)
        tend = pd.Timestamp(end)
        vdates = gen_keys_monthly(tstart, tend, self.asset_lifetime(code, 'E'), self.trade_cal)
        if len(vdates) == 0:
            return

        db = self.facc((TusSdbs.SDB_STOCK_DAILY_INFO.value + code), STOCK_DAILY_INFO_META)

        if flag == IOFLAG.ERASE_ALL:
            for n, dd in enumerate(vdates):
                dtkey = dd.strftime(DATE_FORMAT)
                db.remove(dtkey)
        else:
            for n, dd in enumerate(vdates):
                dtkey = dd.strftime(DATE_FORMAT)
                val = db.load(dtkey, raw_mode=True)
                if val is not None:
                    bvalid = integrity_check_km_vday(dd, val[:, 0], self.trade_cal,
                                                     self.stock_suspend(code), code)
                    if not bvalid:
                        db.remove(dtkey)
        return

    def check_stock_adjfactor(self, code, start, end, flag=IOFLAG.ERASE_INVALID):
        """

        :param code:
        :param start:
        :param end:
        :return:
        """
        tstart = pd.Timestamp(start)
        tend = pd.Timestamp(end)
        vdates = gen_keys_monthly(tstart, tend, self.asset_lifetime(code, 'E'), self.trade_cal)
        if len(vdates) == 0:
            return

        db = self.facc((TusSdbs.SDB_STOCK_ADJFACTOR.value + code), STOCK_ADJFACTOR_META)
        if flag == IOFLAG.ERASE_ALL:
            for n, dd in enumerate(vdates):
                dtkey = dd.strftime(DATE_FORMAT)
                db.remove(dtkey)
        else:
            for n, dd in enumerate(vdates):
                dtkey = dd.strftime(DATE_FORMAT)
                val = db.load(dtkey, raw_mode=True)
                if val is not None:
                    bvalid = integrity_check_km_vday(dd, val[:, 0], self.trade_cal,
                                                     self.stock_suspend(code), code)
                    if not bvalid:
                        db.remove(dtkey)
        return
