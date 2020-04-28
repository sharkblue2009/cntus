"""
行情数据，每日更新
"""
from .utils.xcutils import *
from cntus.xcdb.xcdb import *
from .schema import *
import pandas as pd
from .proloader import TusNetLoader
from .utils.memoize import lazyval


class XcReaderPrice(object):
    """
    行情数据
    """
    master_db = None
    xctus_last_date = None
    trade_cal_index = None
    netloader: TusNetLoader = None

    # def gen_keys_monthly(self, code, start_dt, end_dt, astype=None):
    #     """
    #
    #     :param start_dt:
    #     :param end_dt:
    #     :param astype: asset type
    #     :return:
    #     """
    #     if astype is None:
    #         astype = self.asset_type(code)
    #
    #     limit_start, limit_end = self.asset_lifetime(code, astype)
    #
    #     # 当前交易品种的有效交易日历
    #     today = self.xctus_last_date
    #     tstart = max([limit_start, start_dt])
    #     tend = min([limit_end, end_dt, today])
    #
    #     m_start = pd.Timestamp(year=tstart.year, month=tstart.month, day=1)
    #     m_end = pd.Timestamp(year=tend.year, month=tend.month, day=tend.days_in_month)
    #
    #     vdates = pd.date_range(m_start, m_end, freq='MS')
    #     return vdates
    #
    # def gen_keys_daily(self, code, start_dt, end_dt, astype=None):
    #     """
    #
    #     :param start_dt:
    #     :param end_dt:
    #     :param astype:
    #     :return:
    #     """
    #     if astype is None:
    #         astype = self.asset_type(code)
    #
    #     limit_start, limit_end = self.asset_lifetime(code, astype)
    #     # 当前交易品种的有效交易日历
    #     today = self.xctus_last_date
    #     tstart = max([limit_start, start_dt])
    #     tend = min([limit_end, end_dt, today])
    #
    #     trade_cal = self.trade_cal_index
    #     vdates = trade_cal[(trade_cal >= tstart) & (trade_cal <= tend)]
    #     return vdates

    def get_price_daily(self, code, start: str, end: str, astype=None, flag=IOFLAG.READ_XC):
        """
        按月存取股票的日线数据
        1. 如当月停牌无交易，则存入空数据(或0)
        2. 股票未上市，或已退市，则对应月份键值不存在
        3. 当月有交易，则存储交易日的价格数据
        4. 如交易月键值不存在，但股票状态是正常上市，则该月数据需要下载
        5. refresh两种模式，0: 不更新数据，1: 数据做完整性检查，如不完整则更新，2: 更新start-end所有数据
        如何判断某一月度键值对应的价格数据是否完整：
            1. 对于Index, Fund, 由于不存在停牌情况，因此价格数据的trade_date和当月的trade_calendar能匹配，则数据完整
            2. 对于股票，由于可能停牌，因此，月度价格数据的trade_date加上suspend_date, 和当月trade_calendar匹配，则数据完整
        :param code:
        :param start:
        :param end:
        :return:
        """
        if astype is None:
            astype = self.asset_type(code)

        tstart = pd.Timestamp(start)
        tend = pd.Timestamp(end)
        vdates = gen_keys_monthly(tstart, tend, self.asset_lifetime(code, astype), self.xctus_last_date)
        if len(vdates) == 0:
            return None

        db = self.facc(TusSdbs.SDB_DAILY_PRICE.value + code, EQUITY_DAILY_PRICE_META)

        out = {}

        if flag == IOFLAG.READ_XC:
            for dd in vdates:
                dtkey = dd.strftime(DATE_FORMAT)
                val = db.load(dtkey, KVTYPE.TPV_NARR_2D)
                if val is not None:
                    out[dtkey] = val
                    continue
                ii = self.netloader.set_price_daily(code, MONTH_START(dd), MONTH_END(dd), astype)
                out[dtkey] = db.save(dtkey, ii, KVTYPE.TPV_NARR_2D)
        elif flag == IOFLAG.READ_DBONLY:
            for dd in vdates:
                dtkey = dd.strftime(DATE_FORMAT)
                val = db.load(dtkey, KVTYPE.TPV_NARR_2D)
                if val is not None:
                    out[dtkey] = val
                    continue
        elif flag == IOFLAG.READ_NETONLY:
            for dd in vdates:
                dtkey = dd.strftime(DATE_FORMAT)
                ii = self.netloader.set_price_daily(code, MONTH_START(dd), MONTH_END(dd), astype)
                out[dtkey] = db.save(dtkey, ii, KVTYPE.TPV_NARR_2D)

        # out = db.load_range(vdates[0].strftime(DATE_FORMAT), vdates[-1].strftime(DATE_FORMAT))

        out = list(out.values())
        out = np.vstack(out)
        all_out = pd.DataFrame(data=out, columns=EQUITY_DAILY_PRICE_META['columns'])

        all_out = all_out.set_index('trade_date', drop=True)
        all_out.index = pd.to_datetime(all_out.index, format=DATE_FORMAT)
        all_out = all_out.sort_index(ascending=True)
        all_out = all_out[(all_out.index >= tstart) & (all_out.index <= tend)]
        return all_out

    def get_price_minute(self, code, start, end, freq='1min', astype='E', resample=True, flag=IOFLAG.READ_XC):
        """
        按日存取股票的分钟线数据
        1. 如当日停牌无交易，则存入空数据
        2. 股票未上市，或已退市，则对应日键值不存在
        3. 当日有交易，则存储交易日的数据
        4. 如交易日键值不存在，但股票状态是正常上市，则该月数据需要下载
        5. refresh两种模式，1: 一种是只刷新末月数据，2: 另一种是刷新start-end所有数据
        注： tushare每天有241个分钟数据，包含9:30集合竞价数据
        交易日键值对应的分钟价格数据完整性检查：
            1. 股票， 要么数据完整241条数据，要么为空
            2. 指数和基金，无停牌，因此数据完整。
        :param code:
        :param start:
        :param end:
        :param freq:
        :param resample: if use 1Min data resample to others
        :return:
        """
        if freq not in ['1min', '5min', '15min', '30min', '60min', '120m']:
            return None

        if resample:
            curfreq = '1min'
        else:
            curfreq = freq

        tstart = pd.Timestamp(start)
        tend = pd.Timestamp(end)
        vdates = gen_keys_daily(tstart, tend, self.asset_lifetime(code, astype),
                                self.trade_cal_index, self.xctus_last_date)
        if len(vdates) == 0:
            return None

        db = self.facc( (TusSdbs.SDB_MINUTE_PRICE.value + code + curfreq), EQUITY_MINUTE_PRICE_META,
                        readonly=True)

        out = {}

        if flag == IOFLAG.READ_XC:
            for dd in vdates:
                dtkey = dd.strftime(DATE_FORMAT)
                val = db.load(dtkey, KVTYPE.TPV_NARR_2D)
                if val is not None:
                    out[dtkey] = val
                    continue
                ii = self.netloader.set_price_minute(code, dd, dd, curfreq, astype)
                out[dtkey] = db.save(dtkey, ii, KVTYPE.TPV_NARR_2D)
        elif flag == IOFLAG.READ_DBONLY:
            for dd in vdates:
                dtkey = dd.strftime(DATE_FORMAT)
                val = db.load(dtkey, KVTYPE.TPV_NARR_2D)
                if val is not None:
                    out[dtkey] = val
                    continue
        elif flag == IOFLAG.READ_NETONLY:
            for dd in vdates:
                dtkey = dd.strftime(DATE_FORMAT)
                ii = self.netloader.set_price_minute(code, dd, dd, curfreq, astype)
                out[dtkey] = db.save(dtkey, ii, KVTYPE.TPV_NARR_2D)

        out = list(out.values())
        out = np.concatenate(out)
        all_out = pd.DataFrame(data=out, columns=EQUITY_MINUTE_PRICE_META['columns'])

        all_out = all_out.set_index('trade_time', drop=True)
        all_out.index = pd.to_datetime(all_out.index, format=DATETIME_FORMAT)
        all_out = all_out.sort_index(ascending=True)

        if resample:
            cc = {'1min': 1, '5min': 5, '15min': 15, '30min': 30, '60min': 60, '120min': 120}
            periods = cc[freq]
            all_out = price1m_resample(all_out, periods, market_open=True)

        # if (len(all_out) % 241) != 0:
        #     # Very slow
        #     print('unaligned:{}:-{}'.format(code, len(all_out)))
        #     # all_min_idx = self.trade_cal_index_minutes
        #     # tt_idx = all_min_idx[(all_min_idx >= tstart) & (all_min_idx <= (tend + pd.Timedelta(days=1)))]
        #     tt_idx = session_day_to_min_tus([dd], freq)
        #     all_out = all_out.reindex(index=tt_idx)
        #     all_out.index.name = 'trade_time'
        #     # print('::{}'.format(len(all_out)))

        return all_out

    def get_stock_daily_info(self, code, start, end, flag=IOFLAG.READ_XC):
        """
        Get stock daily information.
        :param code:
        :param start:
        :param end:
        :return:
        """
        tstart = pd.Timestamp(start)
        tend = pd.Timestamp(end)
        vdates = gen_keys_monthly(tstart, tend, self.asset_lifetime(code, 'E'), self.xctus_last_date)
        if len(vdates) == 0:
            return

        db = self.facc( TusSdbs.SDB_STOCK_DAILY_INFO.value + code, STOCK_DAILY_INFO_META)
        out = {}

        if flag == IOFLAG.READ_XC:
            for dd in vdates:
                dtkey = dd.strftime(DATE_FORMAT)
                val = db.load(dtkey, KVTYPE.TPV_NARR_2D)
                if val is not None:
                    out[dtkey] = val
                    continue
                ii = self.netloader.set_stock_daily_info(code, MONTH_START(dd), MONTH_END(dd))
                out[dtkey] = db.save(dtkey, ii, KVTYPE.TPV_NARR_2D)
        elif flag == IOFLAG.READ_DBONLY:
            for dd in vdates:
                dtkey = dd.strftime(DATE_FORMAT)
                val = db.load(dtkey, KVTYPE.TPV_NARR_2D)
                if val is not None:
                    out[dtkey] = val
                    continue
        elif flag == IOFLAG.READ_NETONLY:
            for dd in vdates:
                dtkey = dd.strftime(DATE_FORMAT)
                ii = self.netloader.set_stock_daily_info(code, MONTH_START(dd), MONTH_END(dd))
                out[dtkey] = db.save(dtkey, ii, KVTYPE.TPV_NARR_2D)

        out = list(out.values())
        out = np.concatenate(out)
        all_out = pd.DataFrame(data=out, columns=STOCK_DAILY_INFO_META['columns'])

        all_out = all_out.set_index('trade_date', drop=True)
        all_out.index = pd.to_datetime(all_out.index, format=DATE_FORMAT)
        all_out = all_out.sort_index(ascending=True)
        all_out = all_out[(all_out.index >= tstart) & (all_out.index <= tend)]
        return all_out

    def get_stock_adjfactor(self, code, start: str, end: str, flag=IOFLAG.READ_XC):
        """
        按月存取股票的日线数据
        前复权:
            当日收盘价 × 当日复权因子 / 最新复权因子
        后复权:
            当日收盘价 × 当日复权因子
        :param code:
        :param start:
        :param end:
        :return:
        """
        tstart = pd.Timestamp(start)
        tend = pd.Timestamp(end)
        vdates = gen_keys_monthly(tstart, tend, self.asset_lifetime(code, 'E'), self.xctus_last_date)
        if len(vdates) == 0:
            return

        db = self.facc( TusSdbs.SDB_STOCK_ADJFACTOR.value + code, STOCK_ADJFACTOR_META, readonly=True)
        out = {}

        if flag == IOFLAG.READ_XC:
            for dd in vdates:
                dtkey = dd.strftime(DATE_FORMAT)
                val = db.load(dtkey, KVTYPE.TPV_NARR_2D)
                if val is not None:
                    out[dtkey] = val
                    continue
                ii = self.netloader.set_stock_adjfactor(code, MONTH_START(dd), MONTH_END(dd))
                out[dtkey] = db.save(dtkey, ii, KVTYPE.TPV_NARR_2D)
        elif flag == IOFLAG.READ_DBONLY:
            for dd in vdates:
                dtkey = dd.strftime(DATE_FORMAT)
                val = db.load(dtkey, KVTYPE.TPV_NARR_2D)
                if val is not None:
                    out[dtkey] = val
                    continue
        elif flag == IOFLAG.READ_NETONLY:
            for dd in vdates:
                dtkey = dd.strftime(DATE_FORMAT)
                ii = self.netloader.set_stock_adjfactor(code, MONTH_START(dd), MONTH_END(dd))
                out[dtkey] = db.save(dtkey, ii, KVTYPE.TPV_NARR_2D)

        out = list(out.values())
        out = np.concatenate(out)
        all_out = pd.DataFrame(data=out, columns=STOCK_ADJFACTOR_META['columns'])

        # all_out = pd.concat(out)
        all_out = all_out.set_index('trade_date', drop=True)
        all_out.index = pd.to_datetime(all_out.index, format=DATE_FORMAT)
        all_out = all_out.sort_index(ascending=True)
        all_out = all_out[(all_out.index >= tstart) & (all_out.index <= tend)]
        return all_out

    def get_stock_xdxr(self, code, flag=IOFLAG.READ_XC):
        """
        股票除权除息信息，如需更新，则更新股票历史所有数据。
        :param code:
        :return:
        """
        db = self.facc( TusSdbs.SDB_STOCK_XDXR.value, STOCK_XDXR_META)

        kk = code
        if flag == IOFLAG.READ_XC:
            val = db.load(kk)
            if val is not None:
                return val
            info = self.netloader.set_stock_xdxr(code)
            return db.save(kk, info)
        elif flag == IOFLAG.READ_DBONLY:
            val = db.load(kk)
            return val
        elif flag == IOFLAG.READ_NETONLY:
            info = self.netloader.set_stock_xdxr(code)
            return db.save(kk, info)
        return

    def get_stock_suspend(self, code, flag=IOFLAG.READ_XC):
        """
        股票停复牌信息
        注： 股票存在停牌半天的情况。但也会在suspend列表中体现
        :param code:
        :return:
        """
        db = self.facc( TusSdbs.SDB_STOCK_SUSPEND.value, STOCK_SUSPEND_META, readonly=True)

        kk = code
        if flag == IOFLAG.READ_XC:
            val = db.load(kk)
            if val is not None:
                return val
            info = self.netloader.set_stock_suspend(code)
            return db.save(kk, info)
        elif flag == IOFLAG.READ_DBONLY:
            val = db.load(kk)
            return val
        elif flag == IOFLAG.READ_NETONLY:
            info = self.netloader.set_stock_suspend(code)
            return db.save(kk, info)
        return

    def get_suspend_d(self, start='19900101', end='21000101', flag=IOFLAG.READ_XC):
        """
        股票停复牌信息
        注： 股票存在停牌半天的情况。但也会在suspend列表中体现
        :param code:
        :return:
        """
        tstart = pd.Timestamp(start)
        tend = pd.Timestamp(end)
        trade_cal = self.trade_cal_index
        vdates = trade_cal[(trade_cal >= tstart) & (trade_cal <= tend)]
        if len(vdates) == 0:
            return None

        db = self.facc( TusSdbs.SDB_SUSPEND_D.value, SUSPEND_D_META)
        out = {}

        if flag == IOFLAG.READ_DBONLY:
            for dd in vdates:
                dtkey = dd.strftime(DATE_FORMAT)
                val = db.load(dtkey, KVTYPE.TPV_NARR_2D)
                if val is not None:
                    out[dtkey] = val
                    continue
        elif flag == IOFLAG.READ_XC:
            for dd in vdates:
                dtkey = dd.strftime(DATE_FORMAT)
                val = db.load(dtkey, KVTYPE.TPV_NARR_2D)
                if val is not None:
                    out[dtkey] = val
                    continue
                ii = self.netloader.set_suspend_d(dd)
                out[dtkey] = db.save(dtkey, ii, KVTYPE.TPV_NARR_2D)
        elif flag == IOFLAG.READ_NETONLY:
            for dd in vdates:
                dtkey = dd.strftime(DATE_FORMAT)
                ii = self.netloader.set_suspend_d(dd)
                out[dtkey] = db.save(dtkey, ii, KVTYPE.TPV_NARR_2D)

        out = list(out.values())
        out = np.vstack(out)
        all_out = pd.DataFrame(data=out, columns=SUSPEND_D_META['columns'])
        all_out['suspend_type'] = all_out['suspend_type'].astype(str)
        # all_out['suspend_timing'] = all_out['suspend_timing'].astype(str)

        all_out = all_out.set_index(['trade_date', 'ts_code'], drop=True)
        all_out.index.set_levels(pd.to_datetime(all_out.index.levels[0], format=DATE_FORMAT), level=0, inplace=True)
        all_out = all_out.sort_index(axis=0, level=0, ascending=True)
        all_out = all_out.loc[pd.IndexSlice[tstart:tend, :]]
        # mask = all_out.index.map(lambda x: (x[0]>=tstart) & (x[0]<=tend))
        # all_out = all_out.loc[mask]
        return all_out

    @lazyval
    def suspend_info(self):
        """"""
        log.info('Load stock suspend info.')
        return self.get_suspend_d()


class XcEraserPrice(object):
    def erase_price_daily(self, code, start, end, astype):
        tstart = pd.Timestamp(start)
        tend = pd.Timestamp(end)
        vdates = gen_keys_monthly(tstart, tend, self.asset_lifetime(code, astype), self.xctus_last_date)
        if len(vdates) == 0:
            return

        db = self.facc( TusSdbs.SDB_DAILY_PRICE.value + code,
                        EQUITY_DAILY_PRICE_META)
        for n, dd in enumerate(vdates):
            dtkey = dd.strftime(DATE_FORMAT)
            db.remove(dtkey)
        return

    def erase_price_minute(self, code, start, end, freq='1min', astype=None):
        if freq not in ['1min', '5min', '15min', '30min', '60min', '120m']:
            return None

        tstart = pd.Timestamp(start)
        tend = pd.Timestamp(end)
        vdates = gen_keys_daily(tstart, tend, self.asset_lifetime(code, astype),
                                self.trade_cal_index, self.xctus_last_date)
        if len(vdates) == 0:
            return

        db = self.facc( (TusSdbs.SDB_MINUTE_PRICE.value + code + freq),
                        EQUITY_MINUTE_PRICE_META)

        for n, dd in enumerate(vdates):
            dtkey = dd.strftime(DATE_FORMAT)
            db.remove(dtkey)
        return

    def erase_stock_dayinfo(self, code, start, end):
        """

        :param code:
        :param start:
        :param end:
        :return:
        """
        tstart = pd.Timestamp(start)
        tend = pd.Timestamp(end)
        vdates = gen_keys_monthly(tstart, tend, self.asset_lifetime(code, 'E'), self.xctus_last_date)
        if len(vdates) == 0:
            return

        db = self.facc( (TusSdbs.SDB_STOCK_DAILY_INFO.value + code),
                        STOCK_DAILY_INFO_META)
        for n, dd in enumerate(vdates):
            dtkey = dd.strftime(DATE_FORMAT)
            db.remove(dtkey)
        return

    def erase_stock_adjfactor(self, code, start, end):
        """

        :param code:
        :param start:
        :param end:
        :return:
        """
        tstart = pd.Timestamp(start)
        tend = pd.Timestamp(end)
        vdates = gen_keys_monthly(tstart, tend, self.asset_lifetime(code, astype), self.xctus_last_date)
        if len(vdates) == 0:
            return

        db = self.facc( (TusSdbs.SDB_STOCK_ADJFACTOR.value + code),
                        STOCK_ADJFACTOR_META)
        for n, dd in enumerate(vdates):
            dtkey = dd.strftime(DATE_FORMAT)
            db.remove(dtkey)
        return