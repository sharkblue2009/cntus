"""
财务数据，每季度更新
"""
from .apiwrapper import api_call
from .proloader import TusNetLoader
from .layout import *
from .utils.xcutils import *
from .xcdb.xcdb import *
from .domain import XcDomain


class XcReaderFinance(XcDomain):
    """
    Finance information loader
    """
    master_db = None
    netloader: TusNetLoader = None

    def __init__(self):
        super(XcReaderFinance, self).__init__()

    @api_call
    def get_income(self, code, period, flag=IOFLAG.READ_XC):
        """
        报告期(每个季度最后一天的日期，比如20171231表示年报)
        :param code:
        :param period:
        :param flag:
        :return:
        """
        tperiod = pd.Timestamp(period)
        report_date = QUARTER_END(tperiod)
        dtkey = report_date.strftime(DATE_FORMAT)

        db = self.facc((TusSdbs.SDB_STOCK_FIN_INCOME.value + code), STOCK_FIN_INCOME_META)
        if flag == IOFLAG.READ_DBONLY:
            val = db.load(dtkey)
            return val
        elif flag == IOFLAG.READ_XC:
            val = db.load(dtkey)
            if val is not None:
                return val
            info = self.netloader.set_income(code, dtkey)
            val = db.save(dtkey, info)
            return val
        elif flag == IOFLAG.READ_NETDB:
            info = self.netloader.set_income(code, dtkey)
            val = db.save(dtkey, info)
            return val
        return

    @api_call
    def get_balancesheet(self, code, period, flag=IOFLAG.READ_XC):
        tperiod = pd.Timestamp(period)
        report_date = QUARTER_END(tperiod)
        dtkey = report_date.strftime(DATE_FORMAT)

        db = self.facc((TusSdbs.SDB_STOCK_FIN_BALANCE.value + code), STOCK_FIN_BALANCE_META)
        if flag == IOFLAG.READ_DBONLY:
            val = db.load(dtkey)
            return val
        elif flag == IOFLAG.READ_XC:
            val = db.load(dtkey)
            if val is not None:
                return val
            info = self.netloader.set_balancesheet(code, dtkey)
            val = db.save(dtkey, info)
            return val
        elif flag == IOFLAG.READ_NETDB:
            info = self.netloader.set_balancesheet(code, dtkey)
            val = db.save(dtkey, info)
            return val
        return

    @api_call
    def get_cashflow(self, code, period, flag=IOFLAG.READ_XC):
        tperiod = pd.Timestamp(period)
        report_date = QUARTER_END(tperiod)
        dtkey = report_date.strftime(DATE_FORMAT)

        db = self.facc((TusSdbs.SDB_STOCK_FIN_CASHFLOW.value + code), STOCK_FIN_CASHFLOW_META)
        if flag == IOFLAG.READ_DBONLY:
            val = db.load(dtkey)
            return val
        elif flag == IOFLAG.READ_XC:
            val = db.load(dtkey)
            if val is not None:
                return val
            info = self.netloader.set_cashflow(code, dtkey)
            val = db.save(dtkey, info)
            return val
        elif flag == IOFLAG.READ_NETDB:
            info = self.netloader.set_cashflow(code, dtkey)
            val = db.save(dtkey, info)
            return val
        return

    @api_call
    def get_forcast(self, code, period):
        pass

    @api_call
    def get_express(self, code, period):
        pass

    @api_call
    def get_fina_indicator(self, code, period, flag=IOFLAG.READ_XC):
        tperiod = pd.Timestamp(period)
        report_date = QUARTER_END(tperiod)
        dtkey = report_date.strftime(DATE_FORMAT)

        db = self.facc((TusSdbs.SDB_STOCK_FIN_INDICATOR.value + code),
                       STOCK_FIN_INDICATOR_META)
        if flag == IOFLAG.READ_DBONLY:
            val = db.load(dtkey)
            return val
        elif flag == IOFLAG.READ_XC:
            val = db.load(dtkey)
            if val is not None:
                return val
            info = self.netloader.set_fina_indicator(code, dtkey)
            val = db.save(dtkey, info)
            return val
        elif flag == IOFLAG.READ_NETDB:
            info = self.netloader.set_fina_indicator(code, dtkey)
            val = db.save(dtkey, info)
            return val
        return
