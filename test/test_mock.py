import pytest

from py_balancer_manager import BalancerManagerError


@pytest.mark.asyncio
@pytest.mark.parametrize("version,filename", pytest.helpers.mocked_balancer_manager_files())
async def test_mocked_balancer_manager(mocked_balancer_manager, version, filename):
    await pytest.helpers.update_mocked_balancer_manager(mocked_balancer_manager, filename)
    assert version == mocked_balancer_manager.httpd_version

    # cluster3 object should have 10 routes
    assert len(mocked_balancer_manager.cluster('cluster3').routes) == 10
    # cluster4 object should exist and not throw an exception
    mocked_balancer_manager.cluster('cluster4')


@pytest.mark.asyncio
async def test_with_route_gc(mocked_balancer_manager):
    # update balancer-manager with mock-1
    await pytest.helpers.update_mocked_balancer_manager(mocked_balancer_manager, 'balancer-manager-mock-1.html')

    # cluster3 object should have 10 routes
    assert len(mocked_balancer_manager.cluster('cluster3').routes) == 10
    # cluster4 object should exist and not throw an exception
    mocked_balancer_manager.cluster('cluster4')

    # update balancer-manager with mock-2
    await pytest.helpers.update_mocked_balancer_manager(mocked_balancer_manager, 'balancer-manager-mock-2.html')

    # cluster object should now be gone
    with pytest.raises(BalancerManagerError) as excinfo:
        mocked_balancer_manager.cluster('cluster4')
    assert 'could not locate cluster name in list of clusters: cluster4' in str(excinfo.value)

    # routes route35, route37, and route39 should be removed
    # confirm the number of routes
    assert len(mocked_balancer_manager.cluster('cluster3').routes) == 7
