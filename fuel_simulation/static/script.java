document.getElementById('fuel-button').addEventListener('click', function () {
    const button = this;
    fetch('/toggle_fueling', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'started') {
            button.textContent = 'Stop Fueling';
            button.style.backgroundColor = '#dc3545';
            document.getElementById('status').textContent = 'Fueling in progress...';
            startUpdatingFuelData();
        } else {
            button.textContent = 'Start Fueling';
            button.style.backgroundColor = '#28a745';
            document.getElementById('status').textContent = 'Fueling stopped.';
            stopUpdatingFuelData();
        }
    })
    .catch(error => console.error("Error:", error));
});

let updateInterval;

function startUpdatingFuelData() {
    updateInterval = setInterval(() => {
        fetch('/get_fuel_data')
            .then(response => response.json())
            .then(data => {
                // Update total data
                document.getElementById('total-liters').textContent = data.total_liters.toFixed(3);
                document.getElementById('total-cost').textContent = data.total_cost.toFixed(2);
                document.getElementById('balance').textContent = data.balance.toFixed(2);

                // Update real-time data
                document.getElementById('real-time-liters').textContent = data.real_time_data.liters.toFixed(3);
                document.getElementById('real-time-balance').textContent = data.real_time_data.balance.toFixed(2);

                // Update packet log table
                const packetLogTable = document.getElementById('packet-log').getElementsByTagName('tbody')[0];
                packetLogTable.innerHTML = data.packet_log.map(log => `
                    <tr>
                        <td>${log.time}</td>
                        <td>${log.liters.toFixed(3)}</td>
                        <td>${log.balance.toFixed(2)}</td>
                    </tr>
                `).join('');
            })
            .catch(error => console.error("Error:", error));
    }, 100);  // Update data every 100 ms
}

function stopUpdatingFuelData() {
    clearInterval(updateInterval);
}